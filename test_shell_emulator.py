import os
import unittest
import sys

from io import StringIO
from shell_emulator import VirtualFile, VirtualFileSystem, ShellEmulator

class TestVirtualFileSystem(unittest.TestCase):
    def setUp(self):
        self.fs = VirtualFileSystem()
        self.fs.root.children = {
            'file1.txt': VirtualFile('file1.txt', is_dir=False, permissions=0o644),
            'dir1': VirtualFile('dir1', is_dir=True, permissions=0o755),
        }
        self.fs.root.children['dir1'].children = {
            'file2.txt': VirtualFile('file2.txt', is_dir=False, permissions=0o600),
            'subdir1': VirtualFile('subdir1', is_dir=True, permissions=0o700),
        }
        self.fs.root.children['dir1'].children['subdir1'].children = {
            'file3.txt': VirtualFile('file3.txt', is_dir=False, permissions=0o644),
        }
        self.shell = ShellEmulator('testuser', 'testhost', self.fs)

    def capture_output(self, func, *args, **kwargs):
        captured_output = StringIO()
        original_stdout = sys.stdout
        sys.stdout = captured_output
        try:
            func(*args, **kwargs)
        finally:
            sys.stdout = original_stdout
        return captured_output.getvalue()

    # Тесты для команды ls
    def test_ls_current_directory(self):
        output = self.capture_output(self.fs.ls, [])
        self.assertIn('file1.txt', output)
        self.assertIn('dir1', output)

    def test_ls_specific_directory(self):
        output = self.capture_output(self.fs.ls, ['dir1'])
        self.assertIn('file2.txt', output)
        self.assertIn('subdir1', output)

    # Тесты для команды cd
    def test_cd_into_directory(self):
        self.fs.cd(['dir1'])
        self.assertEqual(self.fs.cwd.name, 'dir1')

    def test_cd_nonexistent_directory(self):
        output = self.capture_output(self.fs.cd, ['nonexistent'])
        self.assertIn('cd: no such file or directory: nonexistent', output)

    # Тесты для команды chmod
    def test_chmod_change_permissions(self):
        self.fs.chmod(['600', 'file1.txt'])
        file = self.fs.root.children['file1.txt']
        self.assertEqual(file.permissions, 0o600)

    def test_chmod_no_write_permission(self):
        self.fs.root.children['file1.txt'].permissions = 0o444
        output = self.capture_output(self.fs.chmod, ['600', 'file1.txt'])
        self.assertIn("chmod: cannot change permissions of 'file1.txt': Permission denied", output)

    # Тесты для команды rm
    def test_rm_file(self):
        self.fs.rm(['file1.txt'])
        self.assertNotIn('file1.txt', self.fs.root.children)

    def test_rm_no_write_permission(self):
        self.fs.root.permissions = 0o555
        output = self.capture_output(self.fs.rm, ['file1.txt'])
        self.assertIn("rm: cannot remove 'file1.txt': Permission denied", output)

    # Тесты для команды find
    def test_find_existing_file(self):
        expected_path = os.path.join('.', 'dir1', 'file2.txt')
        output = self.capture_output(self.fs.find, ['file2.txt'])

        output = output.replace('\\', '/')
        expected_path = expected_path.replace('\\', '/')
        self.assertIn(expected_path, output)

    def test_find_no_permission(self):
        self.fs.root.children['dir1'].permissions = 0o600
        expected_message = f"find: cannot access '{os.path.join('.', 'dir1')}': Permission denied"
        output = self.capture_output(self.fs.find, ['file2.txt'])

        output = output.replace('\\', '/')
        expected_message = expected_message.replace('\\', '/')
        self.assertIn(expected_message, output)

    # Тесты для команды exit
    def test_exit(self):
        with self.assertRaises(SystemExit):
            self.fs.exit([])

    def test_exit_with_message(self):
        with self.assertRaises(SystemExit):
            self.fs.exit(['Goodbye'])

    # Тесты для команды cd с правами доступа
    def test_cd_permission_denied(self):
        self.fs.root.children['dir1'].permissions = 0o666
        output = self.capture_output(self.fs.cd, ['dir1'])
        self.assertIn("cd: permission denied: dir1", output)

    def test_cd_parent_directory(self):
        self.fs.cd(['dir1'])
        self.fs.cd(['..'])
        self.assertEqual(self.fs.cwd, self.fs.root)

    # Тесты для команды ls с правами доступа
    def test_ls_permission_denied(self):
        # Убираем право на чтение для dir1
        self.fs.root.children['dir1'].permissions = 0o311
        output = self.capture_output(self.fs.ls, ['dir1'])
        self.assertIn("ls: cannot open directory 'dir1': Permission denied", output)

    def test_ls_root_directory(self):
        output = self.capture_output(self.fs.ls, ['/'])
        self.assertIn('file1.txt', output)
        self.assertIn('dir1', output)

    # Тесты для функции _navigate_path
    def test_navigate_path_current_directory(self):
        target = self.fs._navigate_path('.')
        self.assertEqual(target, self.fs.cwd)

    def test_navigate_path_parent_directory(self):
        self.fs.cd(['dir1'])
        target = self.fs._navigate_path('..')
        self.assertEqual(target, self.fs.root)

    # Тесты для функции has_permission
    def test_has_permission_read(self):
        file = self.fs.root.children['file1.txt']
        self.assertTrue(self.fs.has_permission(file, 'r'))

    def test_has_permission_write_denied(self):
        file = self.fs.root.children['file1.txt']
        file.permissions = 0o444
        self.assertFalse(self.fs.has_permission(file, 'w'))

    # Тесты для функции _find_parent
    def test_find_parent_root(self):
        parent = self.fs._find_parent(self.fs.root, self.fs.root.children['dir1'])
        self.assertEqual(parent, self.fs.root)

    def test_find_parent_subdirectory(self):
        subdir = self.fs.root.children['dir1'].children['subdir1']
        parent = self.fs._find_parent(self.fs.root, subdir)
        self.assertEqual(parent, self.fs.root.children['dir1'])

    # Тесты для функции _get_path
    def test_get_path_root(self):
        path = self.fs._get_path(self.fs.root)
        self.assertEqual(path, '/')

    def test_get_path_subdirectory(self):
        subdir = self.fs.root.children['dir1'].children['subdir1']
        path = self.fs._get_path(subdir)
        self.assertEqual(path, '/dir1/subdir1')

    # Тесты для функции _get_target_dir
    def test_get_target_dir_existing(self):
        target = self.fs._get_target_dir(['dir1'])
        self.assertEqual(target, self.fs.root.children['dir1'])

    def test_get_target_dir_nonexistent(self):
        output = self.capture_output(self.fs._get_target_dir, ['nonexistent'])
        target = self.fs._get_target_dir(['nonexistent'])
        self.assertIsNone(target)
        expected_message = "ls: cannot access 'nonexistent': No such file or directory"
        self.assertIn(expected_message, output)

 
if __name__ == '__main__':
    unittest.main()
