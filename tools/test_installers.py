"""Windows regression checks that do not download or install anything."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'cmd.exe parsing requires Windows')
class InstallerArguments(unittest.TestCase):
    def parse(self, filename, args, names):
        source = (ROOT / filename).read_text(encoding='utf-8-sig')
        # Run the actual parsing subroutine in isolation, without installation.
        routine = re.search(r'^:parse_args\n(.*?)(?=^:[a-z_]+|\Z)', source, re.M | re.S).group(0)
        script = '@echo off\nsetlocal\n'
        for name in names:
            script += f'set "{name}="\n'
        script += 'call :parse_args %*\nif errorlevel 1 exit /b 1\n'
        script += ''.join(f'echo {name}=%{name}%\n' for name in names)
        script += 'exit /b 0\n' + routine
        with tempfile.TemporaryDirectory(prefix='audio cmd test ', dir=ROOT) as tmp:
            path = Path(tmp) / 'args.cmd'
            path.write_text(script, encoding='utf-8', newline='\r\n')
            return subprocess.run(['cmd.exe', '/d', '/c', str(path), *args], capture_output=True)

    def test_optional_flags_are_not_silently_ignored(self):
        result = self.parse('audio_xtts_universal_installer.cmd',
                            ['--skip-video-models', '--skip-assets', '--help', '--no-pause'],
                            ['SKIP_VIDEO_MODELS', 'SKIP_ASSETS', 'SHOW_HELP', 'NO_PAUSE'])
        self.assertEqual(result.returncode, 0, result.stdout)
        for name in ['SKIP_VIDEO_MODELS', 'SKIP_ASSETS', 'SHOW_HELP', 'NO_PAUSE']:
            self.assertIn((name + '=1').encode(), result.stdout)

    def test_offline_flag_disables_network(self):
        names = ['XTTS_OFFLINE_MODE', 'XTTS_SKIP_PIP_PREFLIGHT', 'XTTS_SKIP_PIP_TOOLING_UPGRADE', 'NO_PAUSE']
        result = self.parse('install_models.cmd', ['--offline', '--no-pause'], names)
        self.assertEqual(result.returncode, 0, result.stdout)
        for name in names:
            self.assertIn((name + '=1').encode(), result.stdout)

    def test_repair_flags(self):
        names = ['SKIP_GIT', 'WITH_VIDEO', 'NO_PAUSE']
        result = self.parse('update_repair_comfyui.cmd', ['--skip-git', '--with-video', '--no-pause'], names)
        self.assertEqual(result.returncode, 0, result.stdout)
        for name in names:
            self.assertIn((name + '=1').encode(), result.stdout)

    def test_unknown_argument_fails(self):
        for filename in ['install_models.cmd', 'audio_xtts_universal_installer.cmd', 'update_repair_comfyui.cmd']:
            self.assertNotEqual(self.parse(filename, ['--invalid-option'], []).returncode, 0)


if __name__ == '__main__':
    unittest.main()
