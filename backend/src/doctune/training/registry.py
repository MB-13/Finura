from doctune.training import colab, kaggle
from doctune.training.base import TrainingBackend

BACKENDS: dict[str, TrainingBackend] = {"colab": colab.backend, "kaggle": kaggle.backend}


def get_backend(name: str) -> TrainingBackend:
    try:
        return BACKENDS[name]
    except KeyError:
        raise ValueError(f"unknown training backend: {name}") from None
