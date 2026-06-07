import sys
import os
from pathlib import Path
import subprocess
from typing import Callable
from contextlib import redirect_stdout, redirect_stderr
import enum
import readline


class Shell:

    def __init__(self):
        self.path_commands: dict[str, Path] = self.get_path_commands()
        self.stdout_target: str | None = None
        self.stderr_target: str | None = None
        self.redirect_mode: RedirectMode = RedirectMode.OVERWRITE
        self.matches: dict[str, str] = {}
        self.autocomplete_commands: list[str] = []
        self._builtins: dict[str, Callable] = {
            "exit": lambda args: exit(0),
            "echo": self._builtin_echo,
            "type": lambda args: self._builtin_type(args[1]) if len(args) > 1 else self.print_not_found(""),
            "pwd": self._builtin_pwd,
            "cd": lambda args: self._builtin_cd(args[1] if len(args) > 1 else ""),
            "history": self._builtin_history
        }

    def _builtin_history(self, args: list[str]) -> None:
        if len(args) >= 3:
            opt: str = args[1]
            path: Path = Path(args[2])
            match opt:
                case "-r":
                    if path.is_file():
                        readline.read_history_file(path)
                        return
                case "-w":
                    readline.write_history_file(path)
                case "-a":
                    readline.append_history_file(path)
            return
        length = readline.get_current_history_length() + 1
        start: int = 1
        if len(args) > 1:
            try:
                count = int(args[1])
                start = length - count
            except ValueError:
                print("Invalid argument")
        print("\n".join([f"{str(i).rjust(5)}  {readline.get_history_item(i)}" for i in range(start, length)]))

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


    def get_path_commands(self) -> dict[str, str]:
        result: dict[str, str] = {}
        path_var: str = os.environ["PATH"]
        for seq in path_var.split(os.pathsep):
            dir_path = Path(seq)
            if not dir_path.exists():
                continue
            for file in dir_path.iterdir():
                if os.access(dir_path / file, os.X_OK):
                    result[file.name] = dir_path / file
        return result


    def is_path_command(self, command: str) -> tuple[bool, Path|None]:

        if command in self.path_commands:
            return True, self.path_commands[command]
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
        for idx, token in enumerate(tokens):
            if token.endswith(">") and len(tokens) > idx + 1:
                token: str = token.replace("1>", ">")
                target: str = tokens[idx+1]
                match token:
                    case ">":
                        self.redirect_mode = RedirectMode.OVERWRITE
                        self.stdout_target = target
                    case ">>":
                        self.redirect_mode = RedirectMode.APPEND
                        self.stdout_target = target
                    case "2>":
                        self.redirect_mode = RedirectMode.OVERWRITE
                        self.stderr_target = target
                    case "2>>":
                        self.redirect_mode = RedirectMode.APPEND
                        self.stderr_target = target
                return tokens[:idx]                

        return tokens


    def handle_input(self, user_input: list[str]) -> None:
        if not user_input:
            self.print_not_found(user_input)
        elif user_input[0] in self._builtins:
            self._builtins[user_input[0]](user_input)
        else:
            valid_external, _ = self.is_path_command(user_input[0])
            if valid_external:
                if self.stdout_target:
                    with open(self.stdout_target, self.redirect_mode.value) as f:
                        subprocess.run(user_input, stdout=f)
                elif self.stderr_target:
                    with open(self.stderr_target, self.redirect_mode.value) as f:
                        subprocess.run(user_input, stderr=f)
                else:
                    subprocess.run(user_input)
            else:
                self.print_not_found(user_input[0])


    def completer(self, text: str, state: int) -> str | None:
        buffer: str = readline.get_line_buffer()

        if state == 0:
            self.matches = {}
            complete_commands: bool = not buffer.endswith(" ") and len(buffer.strip().split()) == 1
            current_display: str = ""

            if complete_commands:
                commands = {key: " " for key in self._builtins.keys() if key.startswith(text)}
                commands.update({key: " " for key in self.path_commands.keys() if key.startswith(text)})
                self.matches = commands
            else:
                if "/" in text: # path is present
                    # find files down that path
                    parts: list[str] = (text.rsplit("/", 1))
                    if not len(parts) == 2:
                        return None
                    dir: Path = Path(os.getcwd()) / parts[0]
                    current_display = parts[0] + "/"
                    search_prefix: str = parts[1]
                else:
                    dir: Path = Path(os.getcwd())
                    search_prefix: str = text

                if dir.is_dir():
                    files: list[Path] = [f for f in dir.iterdir() if f.name.startswith(search_prefix)]

                    if len(files) == 1: # only one file. auto-populate it, then go down its path if there is only one option
                        current: Path = files[0]
                        current_display += current.name
                        """
                        while current.is_dir():
                            sub_files: list[Path] = list(current.iterdir())
                            if len(sub_files) != 1:
                                break
                            current = sub_files[0]
                            current_display += "/" + current.name
                            """
                        self.matches = {current_display: ("/" if current.is_dir() else " ")}
                    elif len(files) > 1:
                        self.matches.update({file.name: ("/" if file.is_dir() else " ") for file in dir.iterdir() if file.name.startswith(text)})

        try:
            match: str = list(self.matches.keys())[state]
            return match  + self.matches[match]
        except IndexError:
            return None


    def main(self):
        
        readline.set_completer_delims(readline.get_completer_delims().replace("/", "").replace("-", "")) # we want these for paths
        readline.set_completer(self.completer)
        if "libedit" in readline.__doc__:
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")

        while True:
            self.buffer = ""
            self.redirect = False
            self.stdout_target = None
            self.stderr_target = None
            self.redirect_mode = RedirectMode.OVERWRITE

            # grab the most recent history item to compare for duplicate suppression
            prev: str|None = None
            curr_hist_len: int = readline.get_current_history_length()
            if curr_hist_len > 1:
                prev = readline.get_history_item(curr_hist_len)
            raw_input: str = input("$ ")
            if prev == raw_input and curr_hist_len == readline.get_current_history_length(): # didn't add
                readline.add_history(raw_input)

            user_input: list[str] = self.parse_input(raw_input)
            if self.stdout_target:
                with open(self.stdout_target, self.redirect_mode.value) as f:
                    with redirect_stdout(f):
                        self.handle_input(user_input)
            elif self.stderr_target:
                with open(self.stderr_target, self.redirect_mode.value) as f:
                    with redirect_stderr(f):
                        self.handle_input(user_input)
            else:
                self.handle_input(user_input)


class ParserState(enum.Enum):
    GENERAL = 1
    SINGLE_QUOTE = 2
    DOUBLE_QUOTE = 3
    ESCAPE = 4


class RedirectMode(enum.Enum):
    OVERWRITE = "w"
    APPEND = "a"


if __name__ == "__main__":
    Shell().main()
