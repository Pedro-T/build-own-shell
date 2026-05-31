import sys


_builtins: dict[str, callable] = {
    "exit": lambda: exit(0)
}


def main():
    while True:
        sys.stdout.write("$ ")
        user_input: str = input()
        if not user_input in _builtins:
            print(f"{user_input}: command not found")
        else:
            _builtins[user_input]()


if __name__ == "__main__":
    main()
