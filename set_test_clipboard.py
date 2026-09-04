#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test helper: set the PC clipboard to a known string (Chinese-safe)."""

import subprocess

TEST_TEXT = 'FOURTH-BG-\u7b2c\u56db\u6b21\u6d4b\u8bd5-77'

subprocess.run(
    ['powershell', '-NoProfile', '-Command', f'Set-Clipboard -Value "{TEST_TEXT}"'],
    check=True,
)
print('PC clipboard set to:', repr(TEST_TEXT))
