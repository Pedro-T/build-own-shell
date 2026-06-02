import sys
import os
from pathlib import Path
import subprocess
from typing import Callable
from contextlib import redirect_stdout


class Shell:

    def __init__(self):
        self.buffer: str = ""
        self.redirect: bool = False
        self.target: str = ""
        self._builtins: dict[str, Callable] = {
            "exit": lambda args: exit(0),
            "echo": self._builtin_echo,
            "type": lambda args: self._builtin_type(args[1]) if len(args) > 1 else self.print_not_found(""),
            "pwd": self._builtin_pwd,
            "cd": lambda args: self._builtin_cd(args[1] if len(args) > 1 else "")
        }
        

    def _builtin_echo(self, args: list[str]) -> None:
        print(" ".join(args[1:]) if len(args) > 1 else "")

    def _builtin_pwd(self, args: list[str]) -> None:
        print(os.getcwd())

    def _builtin_cd(self, req_path: str, absolute=False) -> None:
        if req_path.startswith("~"):
            req_path = req_path.replace("~", os.environ["HOME"])
        path: Path = Path(req_path)
        if not path.exists():
            print(f"cd: {req_path}: No such file or directory")
            return
        os.chdir(path)


    def is_path_command(self,command: str) -> tuple[bool, Path|None]:
        path_var: str = os.environ["PATH"]
        for seq in path_var.split(os.pathsep):
            dir_path = Path(seq)
            if not dir_path.exists():
                continue
            for file in dir_path.iterdir():
                if file.name == command and os.access(dir_path / file, os.X_OK): #matches command and executable
                    return True, dir_path / file
        return False, None


    def _builtin_type(self, command: str) -> None:
        if command in self._builtins:
            print(f"{command} is a shell builtin")
            return
        valid, fullpath = self.is_path_command(command)
        if valid:
            print(f"{command} is {fullpath}")
            return
        self.print_not_found(command)


    def print_not_found(self, command: str) -> None:
        print(f"{command}: not found")


    def parse_input(self, user_input: str) -> list[str]:
        tokens: list[str] = []

        token: str = ""
        curr_quot: str = ""

        i: int = 0

        while i < len(user_input):
            c = user_input[i]
            if c in ['"', "'"] and i < len(user_input) - 1 and user_input[i+1] == c:
                i += 2
                continue
            if c == "\\" and curr_quot != "'":
                if i >= len(user_input) - 1:
                    i+= 1
                elif curr_quot == '"' and user_input[i+1] not in ['"', "\\", "$", "`", "\n"]:
                    token += c
                    i += 1
                else:
                    token += user_input[i+1]
                    i += 2
                continue
            elif c == "'":
                if curr_quot == "'": # we are in a single-quoted string and it just ended
                    curr_quot = ""
                elif not curr_quot: # start a new quoted sequence
                    curr_quot = "'"
                else: # other quoted sequence, just append
                    token += c
            elif c == '"':
                if curr_quot == '"': # we are in a double-quoted string and it just ended
                    curr_quot = ""
                elif not curr_quot: # start a new quoted sequence
                    curr_quot = '"'
                else: # other quoted sequence, just append
                    token += c
            elif c == " ":
                if token and not curr_quot:
                    tokens.append(token)
                    token = ""
                elif curr_quot:
                    token += c
            else:
                token += c
            i += 1
        if token:
            tokens.append(token)
        return tokens


    def handle_input(self, user_input: list[str]) -> None:
        if not user_input:
            self.print_not_found(user_input)
        elif user_input[0] in self._builtins:
            self._builtins[user_input[0]](user_input)
        else:
            valid_external, _ = self.is_path_command(user_input[0])
            if valid_external:
                subprocess.run(user_input)
            else:
                self.print_not_found(user_input[0])


    def main(self):

        while True:
            self.buffer = ""
            self.redirect = False
            self.target = ""
            sys.stdout.write("$ ")
            user_input: list[str] = self.parse_input(input())
            if ">" in user_input:
                idx: int = user_input.index(">") + 1
                if len(user_input) > idx:
                    self.target = user_input[idx]
                    self.redirect = True
                user_input = user_input[:idx-1]
            if self.redirect:
                with open(self.target, "w") as f:
                    with redirect_stdout(f):
                        self.handle_input(user_input)
            else:
                self.handle_input(user_input)


if __name__ == "__main__":
    Shell().main()
