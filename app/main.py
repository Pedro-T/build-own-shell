import sys
import os
from pathlib import Path
import subprocess

_builtins: dict[str, callable] = {
    "exit": lambda args: exit(0),
    "echo": lambda args: print(" ".join(args[1:]) if len(args) > 1 else ""),
    "type": lambda args: _builtin_type(args[1]) if len(args) > 1 else print_not_found("")
}

def is_path_command(command: str) -> tuple[bool, Path|None]:
    path_var: str = os.environ["PATH"]
    for seq in path_var.split(os.pathsep):
        dir_path = Path(seq)
        if not dir_path.exists():
            continue
        for file in dir_path.iterdir():
            if file.name == command and os.access(dir_path / file, os.X_OK): #matches command and executable
                return True, dir_path / file
    return False, None


def _builtin_type(command: str) -> None:
    if command in _builtins:
        print(f"{command} is a shell builtin")
        return
    valid, fullpath = is_path_command(command)
    if valid:
        print(f"{command} is {fullpath}")
        return
    print_not_found(command)

def print_not_found(command: str) -> None:
    print(f"{command}: not found")


def main():
    while True:
        sys.stdout.write("$ ")
        user_input: list[str] = input().split(" ")
        if not user_input:
            print_not_found(user_input)
        elif user_input[0] in _builtins:
            _builtins[user_input[0]](user_input)
        else:
            valid_external, path = is_path_command(user_input[0])
            if valid_external:
                user_input[0] = path
                subprocess.run(user_input)
            else:
                print_not_found(user_input[0])


if __name__ == "__main__":
    main()
