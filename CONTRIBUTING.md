# Contributing

Bug reports, documentation fixes and focused pull requests are welcome.

1. Open an issue describing the problem or proposed change.
2. Create a branch from `main`.
3. Keep credentials, private IP addresses and generated configuration out of commits.
4. Run the checks relevant to your change:

   ```bash
   python3 -m unittest discover -s tests -v
   bash -n install.sh install-macos.sh uninstall.sh uninstall-macos.sh \
     selftest.sh selftest-macos.sh start-mediamtx.sh rotate-credentials.sh \
     tests/e2e-local.sh tests/test-rotate-credentials.sh
   ./tests/test-rotate-credentials.sh
   ```

5. Open a pull request with a concise explanation and verification notes.

By contributing, you agree that your contribution is distributed under the repository's [BSD Advertising Acknowledgement License](LICENSE).
