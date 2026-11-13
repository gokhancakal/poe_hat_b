"""Execute dependency setup with fake commands; never install packages or touch GPIO."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class InstallerDependenciesTests(unittest.TestCase):
    def run_dependencies(self, profile, fail=''):
        source = Path(__file__).with_name('install.sh').read_text()
        apt = source.split('# Install required packages\n', 1)[1].split(
            '# Prepare dependencies', 1)[0]
        pip = source.split('python3 -m venv "$NEXT_VENV"\n', 1)[1].split(
            '# Copy required files', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'bin').mkdir()
            stub = '''#!/bin/bash
printf '%s\\n' "$*" >> "$CALL_LOG"
if [[ -n "$FAIL_MATCH" && "$*" == *"$FAIL_MATCH"* ]]; then
    echo "dependency failed: $*" >&2
    exit 42
fi
'''
            for name in ['apt', 'python3']:
                path = root / 'bin' / name
                path.write_text(stub)
                path.chmod(0o755)
            env = dict(os.environ, PATH=str(root / 'bin') + ':' + os.environ['PATH'],
                       NEXT_VENV=str(root), SOURCE_DIR=str(root),
                       DISPLAY_TYPE=profile, FAN_TYPE='poe', FAIL_MATCH=fail,
                       CALL_LOG=str(root / 'calls'))
            result = subprocess.run(['bash', '-c', 'set -euo pipefail\n' + apt + pip +
                                     '\necho READY_TO_DEPLOY'], env=env,
                                    capture_output=True, text=True)
            return result, (root / 'calls').read_text()

    def test_waveshare_dependencies_and_imports(self):
        result, calls = self.run_dependencies('waveshare-1.3')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('install -y swig liblgpio-dev', calls)
        self.assertIn('-m pip install spidev gpiozero lgpio', calls)
        self.assertIn('-c import spidev, gpiozero, lgpio', calls)
        self.assertIn('READY_TO_DEPLOY', result.stdout)

    def test_poe_does_not_install_spi_gpio_dependencies(self):
        result, calls = self.run_dependencies('poe')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('lgpio', calls)
        self.assertNotIn('swig', calls)
        self.assertNotIn('spidev', calls)

    def test_dependency_failures_stop_before_deployment(self):
        for failure in ['install -y swig liblgpio-dev',
                        '-m pip install spidev gpiozero lgpio',
                        '-c import spidev, gpiozero, lgpio']:
            with self.subTest(failure=failure):
                result, calls = self.run_dependencies('waveshare-1.3', failure)
                self.assertEqual(result.returncode, 42)
                self.assertNotIn('READY_TO_DEPLOY', result.stdout)
                self.assertIn('dependency failed', result.stderr)


if __name__ == '__main__':
    unittest.main()
