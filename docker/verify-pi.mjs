#!/usr/bin/env node
// Verify the named-context-copied Pi environment inside the final image.
//
// CI-only: runs inside the built image (Node is available from the base
// image).  It, in order:
//   1. strictly validates the assembler-evidence envelope and body, then
//      recomputes the canonical evidence-body digest and the assembled output
//      identity and cross-checks both against the independently-attested
//      build arguments;
//   2. rebuilds the canonical tree manifest for the copied tree (excluding the
//      consumer launcher) and requires its content digest to match both the
//      evidence and the PI_TREE_DIGEST build argument, rejecting dangling,
//      escaping, or unexpected symlinks along the way;
//   3. compares every copied-tree entry against the assembler-evidence
//      entries by relative path (kind, file digest, symlink target) and
//      enforces the read-only permission contract (no write bits anywhere;
//      executable bits must match the evidence);
//   4. only then verifies the installed launcher's exact contents,
//      non-writable executable mode, and containment;
//   5. confirms `pi --version`.
//
// The filesystem locations are overridable through environment variables for
// hermetic tests: PI_ROOT (default /opt/pi), PI_ASSEMBLER_EVIDENCE_PATH, and
// PI_LAUNCHER_EVIDENCE_PATH (default /tmp/pi-*-evidence.json).
import {
  readFileSync,
  realpathSync,
  statSync,
  lstatSync,
  readdirSync,
  readlinkSync,
} from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { join, posix, resolve, sep } from "node:path";

function fail(message) {
  console.error(`pi verification failed: ${message}`);
  process.exit(1);
}

function requireEnv(name) {
  const value = process.env[name];
  if (!value) fail(`missing ${name}`);
  return value;
}

const sha256 = (data) => createHash("sha256").update(data).digest("hex");
const isHex64 = (value) =>
  typeof value === "string" && /^[0-9a-f]{64}$/.test(value);

// Canonical, key-sorted, compact JSON — identical to the assembler's
// canonical_json_bytes serialization.
function canonical(value) {
  if (Array.isArray(value)) {
    return "[" + value.map(canonical).join(",") + "]";
  }
  if (value !== null && typeof value === "object") {
    return (
      "{" +
      Object.keys(value)
        .sort()
        .map((k) => JSON.stringify(k) + ":" + canonical(value[k]))
        .join(",") +
      "}"
    );
  }
  return JSON.stringify(value);
}

function requireObject(value, context) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    fail(`${context}: expected an object`);
  }
  return value;
}

function requireExactKeys(value, expected, context) {
  const keys = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (JSON.stringify(keys) !== JSON.stringify(wanted)) {
    fail(
      `${context}: expected fields ${wanted.join(",")}; got ${keys.join(",")}`,
    );
  }
}

function requireHex64Field(obj, key, context) {
  if (!isHex64(obj[key])) {
    fail(`${context}.${key} must be a 64-character hex digest`);
  }
}

const piVersion = requireEnv("PI_VERSION");
const assembledOutputIdentity = requireEnv("PI_ASSEMBLED_OUTPUT_IDENTITY");
const treeDigest = requireEnv("PI_TREE_DIGEST");
const assemblerEvidenceDigest = requireEnv("PI_ASSEMBLER_EVIDENCE_DIGEST");
const launcherEvidenceDigest = requireEnv("PI_LAUNCHER_EVIDENCE_DIGEST");

const piRoot = resolve(process.env.PI_ROOT || "/opt/pi");
const assemblerEvidencePath =
  process.env.PI_ASSEMBLER_EVIDENCE_PATH || "/tmp/pi-assembler-evidence.json";
const launcherEvidencePath =
  process.env.PI_LAUNCHER_EVIDENCE_PATH || "/tmp/pi-launcher-evidence.json";
const launcherPath = join(piRoot, "bin", "pi");

// ── 1. Assembler evidence: strict shape, canonical digest, output identity ──

const assemblerEvidence = requireObject(
  JSON.parse(readFileSync(assemblerEvidencePath, "utf8")),
  "assembler evidence",
);
requireExactKeys(
  assemblerEvidence,
  ["output_identity", "input_identity", "tree_digest", "evidence_digest", "body"],
  "assembler evidence",
);
requireHex64Field(assemblerEvidence, "output_identity", "assembler evidence");
requireHex64Field(assemblerEvidence, "tree_digest", "assembler evidence");
requireHex64Field(assemblerEvidence, "evidence_digest", "assembler evidence");

const inputIdentity = requireObject(
  assemblerEvidence.input_identity,
  "assembler evidence.input_identity",
);
requireHex64Field(inputIdentity, "digest", "assembler evidence.input_identity");

const body = requireObject(assemblerEvidence.body, "assembler evidence.body");
requireExactKeys(
  body,
  [
    "input_identity",
    "tree_digest",
    "tree_entries",
    "packages",
    "omitted_optionals",
    "integrity_less",
    "root_metadata",
    "npm_policy_flags",
  ],
  "assembler evidence.body",
);

// The envelope input_identity and the body input_identity must be the same
// serialized value; the body is otherwise only bound by its digest.
if (canonical(inputIdentity) !== canonical(body.input_identity)) {
  fail("assembler evidence input_identity and body.input_identity disagree");
}

// Retain and validate the assembler's per-entry tree manifest.  Every entry
// must carry exactly the seven manifest fields and paths must be unique.
const evidenceEntries = body.tree_entries;
if (!Array.isArray(evidenceEntries)) {
  fail("assembler evidence.body.tree_entries must be a list");
}
const evidenceByPath = new Map();
for (const entry of evidenceEntries) {
  requireObject(entry, "assembler evidence.body.tree_entries entry");
  requireExactKeys(
    entry,
    ["path", "kind", "digest", "target", "mode", "uid", "gid"],
    "assembler evidence.body.tree_entries entry",
  );
  if (
    typeof entry.path !== "string" ||
    typeof entry.kind !== "string" ||
    typeof entry.digest !== "string" ||
    typeof entry.target !== "string"
  ) {
    fail(
      "assembler evidence.body.tree_entries entry has non-string path/kind/digest/target",
    );
  }
  for (const key of ["mode", "uid", "gid"]) {
    if (!Number.isInteger(entry[key])) {
      fail(
        `assembler evidence.body.tree_entries entry ${entry.path}.${key} must be an integer`,
      );
    }
  }
  if (evidenceByPath.has(entry.path)) {
    fail(`assembler evidence.body.tree_entries has duplicate path ${entry.path}`);
  }
  evidenceByPath.set(entry.path, entry);
}

const recomputedEvidenceDigest = sha256(canonical(body));
if (recomputedEvidenceDigest !== assemblerEvidence.evidence_digest) {
  fail("assembler evidence body digest does not match the envelope");
}
if (recomputedEvidenceDigest !== assemblerEvidenceDigest) {
  fail(
    "assembler evidence body digest does not match PI_ASSEMBLER_EVIDENCE_DIGEST",
  );
}

const recomputedOutputIdentity = sha256(
  canonical({
    input_identity_digest: inputIdentity.digest,
    tree_digest: assemblerEvidence.tree_digest,
    evidence_digest: recomputedEvidenceDigest,
  }),
);
if (recomputedOutputIdentity !== assemblerEvidence.output_identity) {
  fail("assembled output identity does not match the evidence");
}
if (recomputedOutputIdentity !== assembledOutputIdentity) {
  fail("assembled output identity does not match PI_ASSEMBLED_OUTPUT_IDENTITY");
}

// ── 2. Copied-tree validation: canonical manifest over the copied tree ──

function buildTreeEntries(root) {
  const rootReal = realpathSync(root);
  const entries = [];
  const stack = [{ dir: root, prefix: "" }];
  while (stack.length > 0) {
    const { dir, prefix } = stack.pop();
    const names = readdirSync(dir).sort();
    for (const name of names) {
      const abs = join(dir, name);
      const rel = prefix ? `${prefix}/${name}` : name;
      const st = lstatSync(abs);
      const mode = st.mode & 0o777;
      if (st.isSymbolicLink()) {
        const target = readlinkSync(abs);
        // Lexical containment — identical to the assembler's rule.
        if (!target || target.startsWith("/") || target.includes("\\")) {
          fail(`symlink ${rel} has an unsafe target ${JSON.stringify(target)}`);
        }
        const normalized = posix.normalize(posix.join(posix.dirname(rel), target));
        if (normalized === ".." || normalized.startsWith("../")) {
          fail(`symlink ${rel} targets outside the tree`);
        }
        // Complete no-follow resolution: dangling or escaping chains reject.
        let real;
        try {
          real = realpathSync(abs);
        } catch {
          fail(`symlink ${rel} is dangling`);
        }
        if (real !== rootReal && !real.startsWith(rootReal + sep)) {
          fail(`symlink ${rel} resolves outside ${root}`);
        }
        entries.push({
          path: rel,
          kind: "symlink",
          digest: "",
          target,
          mode,
          uid: st.uid,
          gid: st.gid,
        });
      } else if (st.isDirectory()) {
        entries.push({
          path: rel,
          kind: "directory",
          digest: "",
          target: "",
          mode,
          uid: st.uid,
          gid: st.gid,
        });
        stack.push({ dir: abs, prefix: rel });
      } else if (st.isFile()) {
        entries.push({
          path: rel,
          kind: "file",
          digest: sha256(readFileSync(abs)),
          target: "",
          mode,
          uid: st.uid,
          gid: st.gid,
        });
      } else {
        fail(`unsupported special filesystem entry at ${rel}`);
      }
    }
  }
  return entries;
}

const entries = buildTreeEntries(piRoot);
const byPath = new Map(entries.map((e) => [e.path, e]));

// Exclude the consumer launcher file and, when it is the sole occupant, its
// parent directory, so the recomputed digest covers exactly the assembler's
// published tree.
const launcherRel = posix.relative(posix.normalize(piRoot), launcherPath);
if (!byPath.has(launcherRel)) {
  fail(`launcher ${launcherRel} is missing from the copied tree`);
}
byPath.delete(launcherRel);
let parent = posix.dirname(launcherRel);
while (parent !== "." && parent !== "") {
  const hasChildren = [...byPath.keys()].some((p) => p.startsWith(parent + "/"));
  if (!hasChildren) {
    byPath.delete(parent);
    const up = posix.dirname(parent);
    parent = up === "." ? "" : up;
  } else {
    break;
  }
}

const ordered = [...byPath.values()].sort((a, b) =>
  a.path < b.path ? -1 : a.path > b.path ? 1 : 0,
);
const recomputedTreeDigest = sha256(
  canonical(
    ordered.map((e) => ({
      path: e.path,
      kind: e.kind,
      digest: e.digest,
      target: e.target,
    })),
  ),
);
if (recomputedTreeDigest !== assemblerEvidence.tree_digest) {
  fail("copied tree digest does not match the assembler evidence");
}
if (recomputedTreeDigest !== treeDigest) {
  fail("copied tree digest does not match PI_TREE_DIGEST");
}

// ── 3. Per-entry comparison: paths, kinds, digests, targets, permissions ──

// Reject any actual entry absent from the assembler evidence and any
// evidence entry missing from the copied tree.  Kind, file digest, and
// symlink target must match exactly.  UID/GID are intentionally not
// compared (Docker COPY legitimately re-owns the tree); only the write-bit
// contract and the executable bits are enforced.
for (const actual of byPath.values()) {
  const evidenced = evidenceByPath.get(actual.path);
  if (!evidenced) {
    fail(`copied tree has extra entry ${actual.path}`);
  }
  if (actual.kind !== evidenced.kind) {
    fail(
      `entry ${actual.path}: kind ${actual.kind} does not match evidence kind ${evidenced.kind}`,
    );
  }
  if (actual.kind === "file" && actual.digest !== evidenced.digest) {
    fail(`entry ${actual.path}: file digest does not match the evidence`);
  }
  if (actual.kind === "symlink" && actual.target !== evidenced.target) {
    fail(`entry ${actual.path}: symlink target does not match the evidence`);
  }
  if (actual.kind === "file" || actual.kind === "directory") {
    if ((actual.mode & 0o222) !== 0) {
      fail(
        `entry ${actual.path} is writable (mode ${(actual.mode & 0o777).toString(8)})`,
      );
    }
    if ((actual.mode & 0o111) !== (evidenced.mode & 0o111)) {
      fail(`entry ${actual.path}: executable bits differ from the evidence`);
    }
  }
}
for (const evidenced of evidenceEntries) {
  if (!byPath.has(evidenced.path)) {
    fail(`tree entry ${evidenced.path} is missing from the copied tree`);
  }
}

// ── 4. Launcher evidence + installed launcher ──

const launcherEvidence = requireObject(
  JSON.parse(readFileSync(launcherEvidencePath, "utf8")),
  "launcher evidence",
);
if (sha256(canonical(launcherEvidence)) !== launcherEvidenceDigest) {
  fail("launcher evidence digest mismatch");
}
if (launcherEvidence.launcher_path !== launcherPath) {
  fail(
    `launcher evidence path ${launcherEvidence.launcher_path} does not match ${launcherPath}`,
  );
}

const contents = readFileSync(launcherPath);
if (sha256(contents) !== launcherEvidence.contents_sha256) {
  fail("launcher contents mismatch");
}
const mode = statSync(launcherPath).mode & 0o777;
if (mode !== launcherEvidence.mode) {
  fail(
    `launcher mode ${mode.toString(8)} does not match evidence ${launcherEvidence.mode.toString(8)}`,
  );
}
if ((mode & 0o222) !== 0) {
  fail("launcher is writable");
}

const target = resolve(piRoot, launcherEvidence.target);
const realTarget = realpathSync(target);
if (realTarget !== piRoot && !realTarget.startsWith(piRoot + sep)) {
  fail(`launcher target ${realTarget} escapes ${piRoot}`);
}
if (!statSync(realTarget).isFile()) {
  fail(`launcher target ${realTarget} is not a regular file`);
}

// ── 5. `pi --version` matches the reviewed version ──

const version = execFileSync(launcherPath, ["--version"], {
  encoding: "utf8",
}).trim();
if (!version.includes(piVersion)) {
  fail(`pi --version ${JSON.stringify(version)} does not include ${piVersion}`);
}

console.log("pi verification OK");
