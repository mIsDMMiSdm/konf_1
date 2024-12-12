import argparse
import zipfile
import sys
import shlex
import os

class VirtualFile:
    def __init__(self, name, is_dir=False, permissions=0o755):
        self.name = name
        self.is_dir = is_dir
        self.permissions = permissions
        self.children = {}

class VirtualFileSystem:
    def __init__(self, zip_path=None):
        self.root = VirtualFile('/', is_dir=True)
        if zip_path is not None:
            self.load_zip(zip_path)
        self.cwd = self.root


    def load_zip(self, zip_path):
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            for file_info in zipf.infolist():
                path_parts = file_info.filename.strip('/').split('/')
                self._add_file(self.root, path_parts, file_info)

    def _add_file(self, current_dir, path_parts, file_info):
        if not path_parts:
            return
        name = path_parts[0]
        if name not in current_dir.children:
            is_dir = file_info.is_dir()
            permissions = (file_info.external_attr >> 16) & 0o777
            if permissions == 0:
                permissions = 0o755
            current_dir.children[name] = VirtualFile(
                name,
                is_dir=is_dir,
                permissions=permissions
            )
        self._add_file(current_dir.children[name], path_parts[1:], file_info)

    def has_permission(self, file_obj, permission_type):
        mode = file_obj.permissions
        if permission_type == 'r':
            return bool(mode & 0o400)
        elif permission_type == 'w':
            return bool(mode & 0o200)
        elif permission_type == 'x':
            return bool(mode & 0o100)
        return False

    def ls(self, args):
        target_dir = self._get_target_dir(args)
        if target_dir:
            if self.has_permission(target_dir, 'r'):
                for item in target_dir.children.values():
                    print(item.name)
            else:
                print(f"ls: cannot open directory '{target_dir.name}': Permission denied")

    def cd(self, args):
        if not args:
            self.cwd = self.root
            return
        target_dir = self._navigate_path(args[0])
        if target_dir and target_dir.is_dir:
            if self.has_permission(target_dir, 'x'):
                self.cwd = target_dir
            else:
                print(f"cd: permission denied: {args[0]}")
        else:
            print(f"cd: no such file or directory: {args[0]}")

    def exit(self, args):
        sys.exit(0)

    def chmod(self, args):
        if len(args) != 2:
            print("chmod: missing operand")
            return
        try:
            mode = int(args[0], 8)
        except ValueError:
            print(f"chmod: invalid mode: '{args[0]}'")
            return
        target = self._navigate_path(args[1])
        if target:
            if self.has_permission(target, 'w'):
                target.permissions = mode
            else:
                print(f"chmod: cannot change permissions of '{args[1]}': Permission denied")
        else:
            print(f"chmod: cannot access '{args[1]}': No such file or directory")

    def rm(self, args):
        if not args:
            print("rm: missing operand")
            return
        target_path = args[0]
        target_name = os.path.basename(target_path)
        target_parent = self._navigate_path(target_path, parent=True)
        if target_parent is None:
            print(f"rm: cannot remove '{target_path}': No such file or directory")
            return
        if target_name in target_parent.children:
            if self.has_permission(target_parent, 'w'):
                del target_parent.children[target_name]
            else:
                print(f"rm: cannot remove '{target_path}': Permission denied")
        else:
            print(f"rm: cannot remove '{target_path}': No such file or directory")

    def find(self, args):
        search_term = args[0] if args else ''
        self._find_recursive(self.cwd, search_term, current_path='.')

    def _find_recursive(self, current_dir, search_term, current_path):
        if not self.has_permission(current_dir, 'x'):
            print(f"find: cannot access '{current_path}': Permission denied")
            return
        for name, item in current_dir.children.items():
            item_path = os.path.join(current_path, name)
            if search_term == name:
                if self.has_permission(item, 'r'):
                    print(item_path)
                    if item.is_dir:
                        self._list_recursive(item, item_path)
                else:
                    print(f"find: cannot access '{item_path}': Permission denied")
            else:
                if item.is_dir:
                    self._find_recursive(item, search_term, item_path)

    def _list_recursive(self, current_dir, current_path):
        if not self.has_permission(current_dir, 'x'):
            print(f"find: cannot access '{current_path}': Permission denied")
            return
        for name, item in current_dir.children.items():
            item_path = os.path.join(current_path, name)
            if self.has_permission(item, 'r'):
                print(item_path)
            else:
                print(f"find: cannot access '{item_path}': Permission denied")
            if item.is_dir:
                self._list_recursive(item, item_path)

    def _navigate_path(self, path, parent=False):
        parts = path.strip('/').split('/')
        if path.startswith('/'):
            current = self.root
        else:
            current = self.cwd
        if parent:
            if len(parts) > 0:
                parts = parts[:-1]
            else:
                pass
        for part in parts:
            if part == '' or part == '.':
                continue
            elif part == '..':
                parent_dir = self._find_parent(self.root, current)
                if parent_dir:
                    current = parent_dir
                else:
                    current = self.root
            elif part in current.children:
                current = current.children[part]
            else:
                return None
        return current

    def _get_target_dir(self, args):
        if not args:
            return self.cwd
        else:
            target = self._navigate_path(args[0])
            if target and target.is_dir:
                return target
            else:
                print(f"ls: cannot access '{args[0]}': No such file or directory")
                return None

    def _get_path(self, dir_obj):
        path = ''
        while dir_obj != self.root:
            path = '/' + dir_obj.name + path
            dir_obj = self._find_parent(self.root, dir_obj)
        return path or '/'

    def _find_parent(self, current, target):
        for child in current.children.values():
            if child == target:
                return current
            if child.is_dir:
                parent = self._find_parent(child, target)
                if parent:
                    return parent
        return None

class ShellEmulator:
    def __init__(self, user, host, fs):
        self.user = user
        self.host = host
        self.fs = fs
        self.builtins = {
            'ls': self.fs.ls,
            'cd': self.fs.cd,
            'exit': self.fs.exit,
            'chmod': self.fs.chmod,
            'rm': self.fs.rm,
            'find': self.fs.find,
        }

    def run_script(self, script_path):
        try:
            with open(script_path, 'r') as f:
                for line in f:
                    self.execute_command(line.strip())
        except FileNotFoundError:
            print(f"Script file '{script_path}' not found.")

    def execute_command(self, command_line):
        args = shlex.split(command_line)
        if not args:
            return
        command = args[0]
        if command in self.builtins:
            self.builtins[command](args[1:])
        else:
            print(f"{command}: command not found")

    def prompt(self):
        path = self.fs._get_path(self.fs.cwd)
        return f"{self.user}@{self.host}:{path}$ "

    def run(self):
        while True:
            try:
                command_line = input(self.prompt())
                self.execute_command(command_line)
            except EOFError:
                break

def main():
    parser = argparse.ArgumentParser(description='Shell Emulator')
    parser.add_argument('-u', '--user', required=True, help='User name')
    parser.add_argument('-c', '--host', required=True, help='Host name')
    parser.add_argument('-f', '--fs', required=True, help='Path to virtual filesystem zip')
    parser.add_argument('-s', '--script', help='Path to startup script')
    args = parser.parse_args()

    fs = VirtualFileSystem(args.fs)
    shell = ShellEmulator(args.user, args.host, fs)

    if args.script:
        shell.run_script(args.script)

    shell.run()

if __name__ == '__main__':
    main()
