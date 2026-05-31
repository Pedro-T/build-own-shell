import sys


def is_valid_command(cmd: str) -> bool:
    return False


def main():
    sys.stdout.write("$ ")
    user_input: str = input()
    if not is_valid_command(user_input):
        print(f"{user_input}: command not found")



if __name__ == "__main__":
    main()
