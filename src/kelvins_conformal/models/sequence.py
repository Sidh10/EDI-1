"""E7 — recurrent (GRU/LSTM) point predictor over the CDM sequence.

Responsibility (SOFTWARE_ARCHITECTURE.md §2, component ``seqmodels``): a
sequence-aware point predictor in the same architecture family as the closest
prior art (Pinto et al.), so that E8's MC-dropout coverage audit is applied to a
faithful reproduction rather than a strawman.

Masking contract (the part that must not be got wrong)
------------------------------------------------------
Events have 1..k admissible CDMs, so batches are padded. Padding is filled with
``features.PAD_VALUE`` (-999), an obviously-wrong sentinel rather than 0.0, and
every consumer must honour the boolean mask. Two mechanisms enforce this:

  * the recurrent stack runs through ``pack_padded_sequence``, so padded steps are
    never fed to the cell at all; and
  * the output head reads the hidden state **at each event's true final timestep**,
    selected by ``lengths``, not the last padded slot.

``tests/test_sequence_masking.py`` proves the property empirically: perturbing the
padded positions to arbitrary values leaves predictions bitwise unchanged.

Determinism: seeded through ``torch.manual_seed`` plus deterministic algorithms;
training runs single-threaded on CPU (Q-COMP-01: no GPU on this machine).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import torch
from torch import nn


def set_torch_seed(seed: int) -> None:
    """Seed every torch RNG and force deterministic kernels."""
    torch.manual_seed(int(seed))
    torch.cuda.manual_seed_all(int(seed))
    torch.use_deterministic_algorithms(True, warn_only=True)


class SequenceRegressor(nn.Module):
    """GRU/LSTM encoder + MLP head, with dropout usable at inference (E8).

    ``dropout`` is applied to the encoder output before the head. Keeping it as an
    explicit module (rather than an ``nn.RNN`` internal dropout, which only applies
    between stacked layers) is what lets E8 run MC-dropout by enabling train-mode
    dropout at inference without touching anything else.
    """

    def __init__(
        self,
        n_features: int,
        hidden_size: int = 64,
        num_layers: int = 1,
        dropout: float = 0.2,
        cell: str = "gru",
    ) -> None:
        super().__init__()
        self.n_features = int(n_features)
        self.hidden_size = int(hidden_size)
        self.cell_type = cell.lower()

        rnn_cls = {"gru": nn.GRU, "lstm": nn.LSTM}[self.cell_type]
        self.rnn = rnn_cls(
            input_size=n_features,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=(dropout if num_layers > 1 else 0.0),
        )
        self.dropout = nn.Dropout(dropout)
        self.head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size // 2, 1),
        )

    def forward(self, x: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        """Predict one scalar per event.

        ``x`` is (B, T, F) with padding after each event's true length; ``lengths``
        is (B,). Padded steps never reach the cell: the sequence is packed, so the
        RNN processes exactly ``lengths[i]`` steps for event ``i``.
        """
        lengths_cpu = lengths.detach().to("cpu", dtype=torch.int64).clamp(min=1)
        packed = nn.utils.rnn.pack_padded_sequence(
            x, lengths_cpu, batch_first=True, enforce_sorted=False
        )
        out, hidden = self.rnn(packed)
        if self.cell_type == "lstm":
            hidden = hidden[0]
        # hidden: (num_layers, B, H) -> take the final layer's state, which by
        # construction is the state after each sequence's TRUE last timestep.
        final = hidden[-1]
        return self.head(self.dropout(final)).squeeze(-1)


@dataclass
class SequenceResult:
    """A trained sequence model plus its training record."""

    model: SequenceRegressor
    mean: np.ndarray
    std: np.ndarray
    train_losses: list[float] = field(default_factory=list)
    val_losses: list[float] = field(default_factory=list)
    best_epoch: int = 0
    best_val_loss: float = float("inf")
    seed: int = 0
    feature_names: tuple[str, ...] = ()

    def predict(
        self, X: np.ndarray, lengths: np.ndarray, *, batch_size: int = 512
    ) -> np.ndarray:
        """Deterministic point predictions (dropout disabled)."""
        return _forward_all(self.model, X, lengths, batch_size=batch_size, train_mode=False)


def _forward_all(
    model: SequenceRegressor,
    X: np.ndarray,
    lengths: np.ndarray,
    *,
    batch_size: int = 512,
    train_mode: bool = False,
) -> np.ndarray:
    """Run the model over all events, in eval mode unless ``train_mode``.

    ``train_mode=True`` keeps dropout active — this is exactly the MC-dropout hook
    E8 needs, and is why it lives here rather than being re-implemented there.
    """
    model.train(train_mode)
    outs = []
    with torch.no_grad():
        for start in range(0, len(X), batch_size):
            xb = torch.from_numpy(X[start : start + batch_size]).float()
            lb = torch.from_numpy(lengths[start : start + batch_size]).long()
            outs.append(model(xb, lb).cpu().numpy())
    model.eval()
    return np.concatenate(outs) if outs else np.empty(0, dtype=float)


def train_sequence_model(
    X_fit: np.ndarray,
    lengths_fit: np.ndarray,
    y_fit: np.ndarray,
    X_val: np.ndarray,
    lengths_val: np.ndarray,
    y_val: np.ndarray,
    *,
    seed: int,
    n_features: int,
    hidden_size: int = 64,
    num_layers: int = 1,
    dropout: float = 0.2,
    cell: str = "gru",
    batch_size: int = 128,
    max_epochs: int = 60,
    learning_rate: float = 3e-3,
    early_stopping_rounds: int = 10,
    feature_names: tuple[str, ...] = (),
    mean: np.ndarray | None = None,
    std: np.ndarray | None = None,
) -> SequenceResult:
    """Train with early stopping on the INTERNAL validation split.

    Restores the best-validation-loss weights before returning, so the returned
    model is the selected one rather than the last epoch's.
    """
    set_torch_seed(seed)
    torch.set_num_threads(1)

    model = SequenceRegressor(
        n_features=n_features, hidden_size=hidden_size, num_layers=num_layers,
        dropout=dropout, cell=cell,
    )
    optimiser = torch.optim.Adam(model.parameters(), lr=learning_rate)
    loss_fn = nn.MSELoss()

    Xf = torch.from_numpy(X_fit).float()
    Lf = torch.from_numpy(lengths_fit).long()
    Yf = torch.from_numpy(y_fit).float()

    n = len(Xf)
    generator = torch.Generator().manual_seed(int(seed))

    train_losses: list[float] = []
    val_losses: list[float] = []
    best_val = float("inf")
    best_epoch = 0
    best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    since_improved = 0

    for epoch in range(max_epochs):
        model.train(True)
        perm = torch.randperm(n, generator=generator)
        epoch_loss = 0.0
        n_batches = 0
        for start in range(0, n, batch_size):
            idx = perm[start : start + batch_size]
            optimiser.zero_grad()
            pred = model(Xf[idx], Lf[idx])
            loss = loss_fn(pred, Yf[idx])
            loss.backward()
            # Recurrent nets on heavy-tailed targets blow up without clipping;
            # this is stabilisation, not tuning (E7 failure criterion is instability).
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimiser.step()
            epoch_loss += float(loss.item())
            n_batches += 1
        train_losses.append(epoch_loss / max(n_batches, 1))

        val_pred = _forward_all(model, X_val, lengths_val, train_mode=False)
        val_loss = float(np.mean((val_pred - y_val) ** 2))
        val_losses.append(val_loss)

        if val_loss < best_val - 1e-6:
            best_val = val_loss
            best_epoch = epoch
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            since_improved = 0
        else:
            since_improved += 1
            if since_improved >= early_stopping_rounds:
                break

    model.load_state_dict(best_state)
    model.eval()

    return SequenceResult(
        model=model,
        mean=(mean if mean is not None else np.zeros(n_features, dtype=np.float32)),
        std=(std if std is not None else np.ones(n_features, dtype=np.float32)),
        train_losses=train_losses, val_losses=val_losses,
        best_epoch=best_epoch, best_val_loss=best_val,
        seed=int(seed), feature_names=feature_names,
    )
