"""Optional environment adapters. Importing the package never imports a simulator."""

from importlib import import_module


def load_factory(spec):
    """Load explicitly user-configured code, never a model-selected import path."""
    module, separator, name = spec.partition(":")
    if not separator or not module or not name:
        raise ValueError("Factory must be module:function")
    return getattr(import_module(module), name)


def create_environment(name, directory, config):
    if name == "toy":
        from .toy import ToyEnvironment

        return ToyEnvironment(directory, **config)
    if name == "metaworld":
        from .metaworld import MetaWorldEnvironment

        return MetaWorldEnvironment(directory, **config)
    if name == "libero":
        from .robosuite import LiberoEnvironment

        return LiberoEnvironment(directory, **config)
    if name == "robocasa":
        from .robosuite import RoboCasaEnvironment

        return RoboCasaEnvironment(directory, **config)
    if name == "robotwin":
        from .robotwin import RoboTwinEnvironment

        return RoboTwinEnvironment(directory, **config)
    raise ValueError(f"Unknown environment: {name}")
