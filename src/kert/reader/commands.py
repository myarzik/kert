from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SetCommand:
    key: str
    value: str


@dataclass(frozen=True, slots=True)
class GotoCommand:
    percent: float


@dataclass(frozen=True, slots=True)
class QuitCommand:
    pass


Command = SetCommand | GotoCommand | QuitCommand


def parse_command(text: str) -> Command:
    raise NotImplementedError
