# falaw.bridges.skill

Render a Claude SKILL.md (and references) from the falaw tool registry.

The skill is the entry point that teaches Claude Code how to use falaw. It
is generated — never hand-edited at the install location — so adding a
new tool automatically updates the skill the next time we run
`write_skill_files()`.

### Functions

| [`build_skill_md`](#falaw.bridges.skill.build_skill_md)([tools])       | Render the SKILL.md content from the tool registry.                 |
|--------------------------------------------------------------------------------|---------------------------------------------------------------------|
| [`write_skill_files`](#falaw.bridges.skill.write_skill_files)(target_dir) | Write SKILL.md (and a small references/ folder) under `target_dir`. |

### falaw.bridges.skill.build_skill_md(tools=None)

Render the SKILL.md content from the tool registry.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### falaw.bridges.skill.write_skill_files(target_dir)

Write SKILL.md (and a small references/ folder) under `target_dir`.

Returns the path written.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
