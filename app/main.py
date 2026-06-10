import os
from pathlib import Path
import subprocess
from typing import Callable
from contextlib import redirect_stdout, redirect_stderr
import enum
import readline
from typing import Any
from re import Pattern, compile
from dataclasses import dataclass
from time import time


VAR_PATTERN: Pattern = compile(r"^[A-Za-z_]{1}[A-Za-z0-9_]*$")


@dataclass
class Job:
    process: subprocess.Popen
    start_time: float


class JobManager:
    def __init__(self):
        self.jobs: list[Job] = []
    
    def add_job(self, command: str) -> None:
        job: Job = Job(subprocess.Popen(command, shell=True), time())
        
        slot: int = -1
        for i in range(len(self.jobs)):
            if self.jobs[i] == None:
                self.jobs[i] = job
                slot = i+1
                break
        if slot < 0:
            self.jobs.append(job)
            slot = len(self.jobs)
        print(f"[{slot}] {job.process.pid}")


    def list_jobs(self) -> None:
        idx: int = 0

        sorted_starts: list[Job] = sorted(self.jobs, key=lambda job: job.start_time, reverse=True)

        while idx < len(self.jobs):
            job: Job = self.jobs[idx]
            if not job:
                continue
            state: int|None = job.process.poll()
            state_msg: str = "Running" if state is None else "Done"
            msg: str = f"[{idx+1}]{'+' if job == sorted_starts[0] else '-' if (len(sorted_starts) > 1 and job == sorted_starts[1]) else " "}  {state_msg.ljust(24)}{job.process.args}"
            print(msg)
            if state is not None:
                self.jobs[idx] = None
            idx += 1


class Shell:

    def __init__(self):
        self.job_manager = JobManager()
        self.path_commands: dict[str, Path] = self.get_path_commands()
        self.stdout_target: str | None = None
        self.stderr_target: str | None = None
        self.redirect_mode: RedirectMode = RedirectMode.OVERWRITE
        self.matches: dict[str, str] = {}
        self.autocomplete_commands: list[str] = []
        self.history_append_counter: int = 0
        self._builtins: dict[str, Callable] = {
            "exit": lambda args: self._builtin_exit(args),
            "echo": self._builtin_echo,
            "type": lambda args: self._builtin_type(args[1]) if len(args) > 1 else self.print_not_found(""),
            "pwd": self._builtin_pwd,
            "cd": lambda args: self._builtin_cd(args[1] if len(args) > 1 else ""),
            "history": self._builtin_history,
            "declare": self._builtin_declare,
            "complete": self._builtin_complete,
            "jobs": self._builtin_jobs
        }
        self._completers: dict[str, str] = {}
        self._vars: dict[str, Any] = {}


    def _builtin_jobs(self, args: list[str]) -> None:
        self.job_manager.list_jobs()


    def _builtin_complete(self, args: list[str]) -> None:
        if len(args) < 2:
            return
        match args[1]:
            case "-C":
                try:
                    self._completers[args[3]] = args[2]
                except IndexError:
                    print("Invalid arguments")
            case "-p":
                try:
                    if args[2] in self._completers:
                        print(f"complete -C \'{self._completers[args[2]]}\' {args[2]}")
                    else:
                        print(f"complete: {args[2]}: no completion specification")
                except IndexError:
                    print("Invalid arguments")
            case "-r":
                try:
                    if args[2] in self._completers:
                        del self._completers[args[2]]
                    else:
                        print(f"complete: {args[2]}: no completion specification")
                except IndexError:
                    print("Invalid syntax")
            case _:
                print("Invalid arguments")


    def _is_valid_var(self, text: str) -> bool:
        return VAR_PATTERN.fullmatch(text) is not None


    def _builtin_declare(self, args: list[str]) -> None:
        if len(args) < 2:
            return
        if len(args) > 2 and args[1] == "-p":
            var: str = args[2]
            if var not in self._vars:
                print(f"declare: {var}: not found")
            else:
                print(f"declare -- {var}=\"{self._vars[var]}\"")
        elif len(args) == 2 and "=" in args[1]:
            parts: list[str] = args[1].split("=")
            if not parts[0] or not parts[1]:
                print("Invalid syntax")
                return
            if not self._is_valid_var(parts[0]):
                print(f"declare: `{args[1]}': not a valid identifier")
            self._vars[parts[0]] = parts[1]
            

    def _builtin_exit(self, args: list[str]) -> None:
        path: str = os.environ.get("HISTFILE")
        if path:
            readline.write_history_file(path)
        exit(0)

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
                    readline.append_history_file(self.history_append_counter, path)
                    self.history_append_counter = 0
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
        state: ParserState = ParserState.GENERAL

        i: int = 0

        while i < len(user_input):
            c = user_input[i]

            if state != ParserState.SINGLE_QUOTE and c == "$":
                if i == len(user_input) - 1:
                    i += 1
                    continue

                i += 1 # advance to char after $
                term_char: str = " "
                if user_input[i] == "{": #if this is {} advance another char and change end char
                    i += 1
                    term_char = "}"

                buffer: str = ""
                while i < len(user_input) and user_input[i] != term_char:
                    buffer += user_input[i]
                    i += 1

                if buffer and buffer in self._vars:
                    token += self._vars[buffer]
                if term_char == "}":
                    i += 1
                continue


            if c in ['"', "'"] and i < len(user_input) - 1 and user_input[i+1] == c:
                i += 2
                continue
            elif c == "\\" and state != ParserState.SINGLE_QUOTE:
                if i >= len(user_input) - 1:
                    i+= 1
                elif state == ParserState.DOUBLE_QUOTE and user_input[i+1] not in ['"', "\\", "$", "`", "\n"]:
                    token += c
                    i += 1
                else:
                    token += user_input[i+1]
                    i += 2
                continue
            elif c == "'":
                if state == ParserState.SINGLE_QUOTE: # we are in a single-quoted string and it just ended
                    state = ParserState.GENERAL
                elif state == ParserState.GENERAL: # start a new quoted sequence
                    state = ParserState.SINGLE_QUOTE
                else: # other quoted sequence, just append
                    token += c
            elif c == '"':
                if state == ParserState.DOUBLE_QUOTE: # we are in a double-quoted string and it just ended
                    state = ParserState.GENERAL
                elif state == ParserState.GENERAL: # start a new quoted sequence
                    state = ParserState.DOUBLE_QUOTE
                else: # other quoted sequence, just append
                    token += c
            elif c == " ":
                if token and state == ParserState.GENERAL:
                    tokens.append(token)
                    token = ""
                elif state != ParserState.GENERAL:
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
            if user_input[-1] == "&":
                self.job_manager.add_job(" ".join(user_input[:-1]))
                return
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
                buff_parts: list[str] = buffer.split()
                first: str = buff_parts[0]
                last: str = buff_parts[-2] if len(buff_parts) > 2 else first
                
                if first in self._completers:
                    path: str = self._completers[first]
                    proc: subprocess.CompletedProcess = subprocess.run(
                        [path, first, text, last], 
                        capture_output=True, 
                        text=True,
                        env={
                            **os.environ,
                            "COMP_LINE": buffer,
                            "COMP_POINT": str(len(buffer))
                        })
                    output: str = proc.stdout
                    self.matches = {option: " " for option in output.split()}
                    try:
                        match: str = list(self.matches.keys())[state]
                        return match  + self.matches[match]
                    except IndexError:
                        return None

                elif "/" in text: # path is present
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
                        self.matches = {current_display: ("/" if current.is_dir() else " ")}
                    elif len(files) > 1:
                        self.matches.update({file.name: ("/" if file.is_dir() else " ") for file in dir.iterdir() if file.name.startswith(text)})
            

        try:
            match: str = list(self.matches.keys())[state]
            return match  + self.matches[match]
        except IndexError:
            return None


    def main(self):
        file: str = os.environ.get("HISTFILE")
        if file and Path(file).is_file():
            readline.read_history_file(file)
        
        readline.set_completer_delims(readline.get_completer_delims().replace("/", "").replace("-", "")) # we want these for paths
        readline.set_completer(self.completer)
        if "libedit" in readline.__doc__:
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")

        while True:
            self.history_append_counter += 1
            self.buffer = ""
            self.redirect = False
            self.stdout_target = None
            self.stderr_target = None
            self.redirect_mode = RedirectMode.OVERWRITE

            raw_input: str = input("$ ")
            
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


class JobState(enum.Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    DONE = "Done"


class RedirectMode(enum.Enum):
    OVERWRITE = "w"
    APPEND = "a"


if __name__ == "__main__":
    Shell().main()
