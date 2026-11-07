#!/usr/bin/env python3
"""Exercise embedded-video recovery using independent media/checksum fixtures."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('motion', Path(__file__).with_name('restore-immich-motion.py'))
motion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(motion)


def box(name, data):
    return (len(data) + 8).to_bytes(4, 'big') + name + data


class MotionRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'upload').mkdir()
        self.clip = box(b'ftyp', b'mp42\0\0\0\0') + box(b'mdat', b'actual video bytes')
        self.photo = self.root / 'upload/photo.jpg'
        self.original = b'JPEG fixture' + self.clip + b'nonvideo trailer'
        self.photo.write_bytes(self.original)
        self.row = {'photo': '/data/upload/photo.jpg', 'video': '/data/encoded-video/clip.mp4',
                    'algorithm': 'sha1', 'checksum': hashlib.sha1(self.clip).hexdigest()}

    def test_read_only_then_write_with_trailer(self):
        result = motion.recover(self.root, [self.row])
        self.assertEqual(result['recoverable'], 1)
        self.assertFalse((self.root / 'encoded-video').exists())
        result = motion.recover(self.root, [self.row], apply=True)
        self.assertEqual(result['written'], 1)
        self.assertEqual((self.root / 'encoded-video/clip.mp4').read_bytes(), self.clip)
        self.assertEqual(self.photo.read_bytes(), self.original)
        self.assertEqual(motion.recover(self.root, [self.row], apply=True)['verified_existing'], 1)

    def test_sha256_and_no_trailer(self):
        self.photo.write_bytes(b'JPEG fixture' + self.clip)
        self.row.update(algorithm='sha256', checksum=hashlib.sha256(self.clip).hexdigest())
        self.assertEqual(motion.recover(self.root, [self.row])['recoverable'], 1)

    def test_wrong_checksum_cannot_create_video(self):
        self.row['checksum'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'No unique'):
            motion.recover(self.root, [self.row], apply=True)
        self.assertFalse((self.root / 'encoded-video').exists())

    def test_existing_different_clip_is_preserved(self):
        target = self.root / 'encoded-video/clip.mp4'
        target.parent.mkdir()
        target.write_bytes(b'other existing video')
        with self.assertRaisesRegex(ValueError, 'refusing replacement'):
            motion.recover(self.root, [self.row], apply=True)
        self.assertEqual(target.read_bytes(), b'other existing video')

    def test_path_escape_and_wrong_directory(self):
        for target in ('/data/../escape.mp4', '/data/upload/clip.mp4', '/elsewhere/clip.mp4'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                motion.recover(self.root, [{**self.row, 'video': target}], apply=True)

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / 'encoded-video').symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'escapes'):
                motion.recover(self.root, [self.row], apply=True)
            self.assertEqual(list(Path(outside).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
