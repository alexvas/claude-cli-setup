## 1. RED: SIGTERM ownership and lifecycle contracts

- [ ] 1.1 Add daemon-independent tests that deliver an injected SIGTERM termination request during an active interactive run and assert cleanup targets exactly the allocated container name.
- [ ] 1.2 Add an ordering test proving forced container removal is attempted while the runtime projection still exists, the attached Docker client is reaped, and projection cleanup follows.
- [ ] 1.3 Add tests for an already-removed container and cleanup-command failure, asserting both preserve status 143 and still reap the client and remove the projection.
- [ ] 1.4 Add isolation tests proving SIGTERM cleanup neither enumerates nor removes other `pi-N` containers.
- [ ] 1.5 Add facade tests for clean SIGTERM termination with exit status 143 and supplemental cleanup diagnostics that do not replace the primary outcome.
- [ ] 1.6 Add regression coverage proving container-local `Ctrl-C` remains ordinary interactive behavior and does not invoke facade-termination cleanup.
- [ ] 1.7 Confirm focused tests reach the intentional unimplemented signal/cleanup boundaries without invoking Docker or real OS signals.

## 2. GREEN: Facade SIGTERM cleanup

- [ ] 2.1 Introduce a dedicated internal facade-termination signal/control-flow type and a scoped, injectable SIGTERM handler adapter.
- [ ] 2.2 Introduce a narrow injected owned-container cleanup protocol and structured result/error representation.
- [ ] 2.3 Implement exact production cleanup using `docker rm --force <allocated-name>` in captured mode, treating an absent target as idempotent success.
- [ ] 2.4 Ensure interruption of the interactive wait cannot orphan the attached `docker run` client; terminate and reap it through an injectable managed-process boundary.
- [ ] 2.5 Handle facade SIGTERM inside the projection transaction: remove the exact container, reap the Docker client, then leave the context to remove the projection.
- [ ] 2.6 Scope SIGTERM handling to the active run on the main thread and restore the previous handler on success, failure, and termination.
- [ ] 2.7 Wire production signal and cleanup adapters through the constructor facade while preserving daemon-independent test injection.
- [ ] 2.8 Render cleanup failures only as supplemental diagnostics and terminate with status 143 without converting SIGTERM into success or ordinary operational status.
- [ ] 2.9 Keep container-local `Ctrl-C`, normal success, ordinary nonzero exit, dry-run, captured mode, and process-launch-error behavior unchanged.
- [ ] 2.10 Re-run focused launcher, facade, acceptance, run-vector, and runtime-lifecycle tests until green.

## 3. INTROSPECT: Signal and cleanup review

- [ ] 3.1 Verify the SIGTERM transaction owns one exact allocated name and never performs prefix-based discovery or broad cleanup.
- [ ] 3.2 Verify cleanup ordering keeps the projection available until forced container removal is attempted and the Docker client is reaped.
- [ ] 3.3 Verify cleanup is idempotent and secondary cleanup failures cannot replace status 143.
- [ ] 3.4 Verify the prior SIGTERM handler is restored and no signal behavior changes for build, verify, doctor, evidence, or inactive launcher code.
- [ ] 3.5 Verify success, nonzero exit, `OSError`, facade SIGTERM, early SIGTERM before container creation, and cleanup failure all have explicit process/container/projection lifecycle behavior.
- [ ] 3.6 Confirm inherited streams, container-local `Ctrl-C`, terminal restoration, captured diagnostics, evidence redaction/bounds, Docker argv, mounts, project numbering, and gateway behavior remain unchanged.
- [ ] 3.7 Confirm uncatchable `SIGKILL` and host failure remain explicitly outside the guarantee.

## 4. VALIDATE: Automated and Docker-host acceptance

- [ ] 4.1 Run focused daemon-independent launcher, facade, acceptance, run-vector, and runtime-lifecycle tests.
- [ ] 4.2 Run the complete unit suite with `python3 -m unittest discover -s tests -q`.
- [ ] 4.3 Run `python3 -m compileall -q docker tests`.
- [ ] 4.4 Run `openspec validate cleanup-interrupted-container --strict` and `git diff --check`.
- [ ] 4.5 On a Docker host, start a default interactive launch, send `SIGTERM` directly to the facade PID, and confirm facade exit status 143 with a restored terminal.
- [ ] 4.6 Confirm the terminated facade's container, attached Docker client, and runtime projection no longer exist while unrelated `pi-N` containers remain running.
- [ ] 4.7 Confirm `Ctrl-C` inside the interactive container still interrupts only the in-container foreground application and leaves the session attached.
- [ ] 4.8 Repeat normal `exit`, captured exit 7, and external `docker stop` scenarios to confirm existing behavior remains unchanged.
