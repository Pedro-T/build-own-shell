import sys


_builtins: dict[str, callable] = {
    "exit": lambda args: exit(0),
    "echo": lambda args: print(" ".join(args[1:]) if len(args) > 1 else ""),
    "type": lambda args: _builtin_type(args[1]) if len(args) > 1 else print_not_found("")
}

def _builtin_type(command: str) -> None:
    if command in _builtins:
        print(f"{command} is a shell builtin")
    else:
        print_not_found(command)

def print_not_found(command: str) -> None:
    print(f"{command}: not found")


def main():
    while True:
        sys.stdout.write("$ ")
        user_input: list[str] = input().split(" ")
        if not user_input or user_input[0] not in _builtins:
            print_not_found(user_input[0])
        else:
            _builtins[user_input[0]](user_input)


if __name__ == "__main__":
    main()
