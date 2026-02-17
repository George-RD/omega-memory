# OMEGA Fork Maintenance Guide

All fork-only changes live on the `fork/security` branch and merge into local `main`.
They never go upstream.

## Branch Structure

    upstream/main            <- the real omega-memory repo
      |
    main (local)             <- merges upstream + fork/security
      |
    fork/security            <- your security scripts, hash pins, .gitignore

## Syncing Upstream Changes

    cd ~/repos/omega-memory

    # 1. Run the pre-sync security check
    bash scripts/check_upstream_before_sync.sh

    # 2. If all clear, merge upstream
    git fetch upstream
    git merge upstream/main

    # 3. Re-run model verification
    python3 scripts/secure_model_download.py --check-only

    # 4. Re-run boot check
    python3 scripts/omega_boot_check.py

    # 5. Optional deep scan
    bandit -r src/ -ll --quiet

If the security check flags anything, read the diffs manually before merging.

## After Upstream Changes the Model

    # 1. Delete cached model
    rm -rf ~/.cache/omega/models/bge-small-en-v1.5-onnx/

    # 2. Edit scripts/secure_model_download.py — set all sha256 values to None

    # 3. Download fresh (prints new hashes)
    python3 scripts/secure_model_download.py --force

    # 4. Copy the printed SHA256 values back into MODEL_FILES in the script

    # 5. Commit to fork/security
    git checkout fork/security
    git add scripts/secure_model_download.py
    git commit -m "fork: update pinned model hashes for new upstream model"
    git checkout main
    git merge fork/security --no-edit

## Adding Fork-Only Changes

    git checkout fork/security
    # make changes
    git add <files>
    git commit -m "fork: description"
    git checkout main
    git merge fork/security --no-edit

## Making an Upstream PR

    # Branch from main after syncing upstream
    git checkout main
    git fetch upstream && git merge upstream/main
    git checkout -b feature/my-improvement

    # Work, commit, push to YOUR fork
    git push -u origin feature/my-improvement
    # Open PR on GitHub against omega-memory/omega-memory:main

fork/security changes won't be in the feature branch.

## Script Reference

    check_upstream_before_sync.sh    7-check security audit       Before merging upstream
    secure_model_download.py         Download model + hash verify  First install, model changes
    secure_model_download.py --check Verify existing model         After sync, periodic
    omega_boot_check.py              System health check           Before starting, after updates
    bandit -r src/ -ll               Static analysis               After sync, periodic

## File Locations

    OMEGA database       ~/.omega/omega.db
    Model cache          ~/.cache/omega/models/bge-small-en-v1.5-onnx/
    Fork repo            ~/repos/omega-memory/
    Security scripts     ~/repos/omega-memory/scripts/

## Troubleshooting

HASH MISMATCH: Upstream changed the model. Follow "After Upstream Changes the Model" above.

SIZE MISMATCH: Update expected_size_bytes in secure_model_download.py, re-pin hash.

Bandit new issues: Most SQL findings are false positives (parameterized queries). Review manually.

Permission errors: chmod 700 ~/.omega && chmod 600 ~/.omega/omega.db
