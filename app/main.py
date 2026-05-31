import sys


_builtins: dict[str, callable] = {
    "exit": lambda args: exit(0),
    "echo": lambda args: print(" ".join(args[1:]) if len(args) > 1 else "")
}


def main():
    while True:
        sys.stdout.write("$ ")
        user_input: list[str] = input().split(" ")
        if not user_input or user_input[0] not in _builtins:
            print(f"{user_input[0]}: command not found")
        else:
            _builtins[user_input[0]](user_input)


if __name__ == "__main__":
    main()
