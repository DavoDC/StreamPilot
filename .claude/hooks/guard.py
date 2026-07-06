import sys
import json
import re
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
d = json.loads(sys.stdin.buffer.read())
tn = d.get('tool_name', '')
ti = d.get('tool_input', {})

# chr(8212)=em dash, chr(8211)=en dash - avoid literals so guard does not self-trigger


def block(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)


ALLOWED_WRITE_ROOTS = [
    'c:/users/david/githubrepos',
    '/c/users/david/githubrepos',
    'c:/users/david/.claude',
    '/c/users/david/.claude',
    '/tmp',
]


def path_allowed(p):
    p = p.replace('\\', '/').lower().rstrip('/')
    if '..' in p or p.count('/') > 100:
        return False
    return any(p.startswith(r) for r in ALLOWED_WRITE_ROOTS)


if tn == 'CronCreate':
    prompt = ti.get('prompt', '')
    safe_patterns = [
        '<<autonomous-loop',
        'check-budget',
        'ScheduleWakeup',
        'push origin',
        '/loop',
    ]
    is_safe = any(p in prompt for p in safe_patterns)
    if not is_safe and len(prompt) > 50:
        block('BLOCKED: CronCreate prompt must use whitelisted safe patterns (<<autonomous-loop, check-budget, ScheduleWakeup, /loop). Arbitrary prompts cannot be validated outside session context.')

elif tn == 'Bash':
    cmd = ti.get('command', '')
    cmd_part = cmd.split('-m')[0] if '-m' in cmd else cmd.split('<<')[0] if '<<' in cmd else cmd
    if re.search(r'\bgit\b.*\spush(\s|$)', cmd_part):
        block('BLOCKED: Claude cannot push. User pushes from host after reviewing commits locally.')
    if re.search(r'git\s+.*--no-verify', cmd):
        block('BLOCKED: --no-verify not allowed.')
    if re.search(r'git\s+push\s+.*--(force|force-with-lease)', cmd):
        block('BLOCKED: Force push not allowed.')
    if re.search(r'git\s+reset\s+--hard', cmd):
        block('BLOCKED: git reset --hard is destructive.')
    if re.search(r'rm\s+-rf\s+(/c/Users|/home|~|C:\\\\|/workspace)', cmd, re.I):
        block('BLOCKED: rm -rf on home/user dirs not allowed.')
    if re.search(r'\brmdir\s+/s\b|\brd\s+/s\b', cmd, re.I):
        block('BLOCKED: rmdir /s not allowed.')
    if 'Remove-Item' in cmd and '-Recurse' in cmd and ('/Users' in cmd or '\\Users' in cmd):
        block('BLOCKED: Remove-Item -Recurse on user dirs not allowed.')
    if re.search(r'\breg\s+(add|delete|import)\b', cmd, re.I):
        block('BLOCKED: Registry modification not allowed in yolo mode.')
    if re.search(r'\bsc\s+(stop|delete|config|create)\b', cmd, re.I):
        block('BLOCKED: Service control not allowed in yolo mode.')
    if re.search(r'\bnet\s+(user|localgroup|accounts)\b', cmd, re.I):
        block('BLOCKED: User/group management not allowed in yolo mode.')
    if re.search(r'\bschtasks\s+/create\b', cmd, re.I):
        block('BLOCKED: Creating scheduled tasks not allowed in yolo mode.')
    if re.search(r'(curl|wget|iwr|Invoke-WebRequest)\s+.+\|\s*(bash|sh|python|python3|powershell|pwsh)', cmd, re.I):
        block('BLOCKED: Pipe-to-shell from network download not allowed.')

elif tn in ('Write', 'Edit', 'NotebookEdit'):
    fp = ti.get('file_path', '') or ti.get('notebook_path', '')
    c = ti.get('content', '') + ti.get('new_string', '')
    bn = os.path.basename(fp)

    if bn == 'settings.json' and ('Claude_Workspace' in fp or 'Claude_Workspace' in os.path.normpath(fp)):
        if '.claude' in fp or '.claude' in os.path.normpath(fp):
            if 'disableAllHooks' in c and 'true' in c:
                block('BLOCKED: Cannot disable all hooks via settings.json. Edit manually if absolutely needed.')

    fp_norm = fp.replace('\\', '/').lower()
    gdrive_md = fp_norm.startswith('c:/users/david/google drive') and fp_norm.endswith('.md')
    if fp and not path_allowed(fp) and not gdrive_md:
        block('BLOCKED: Write/Edit outside allowed scope: ' + fp + '\nAllowed roots: GitHubRepos and .claude only.')

    if chr(8212) in c or chr(8211) in c:
        block('BLOCKED: Em/en dashes found. Use regular dashes (-) instead.')

    if re.search(r'\.(env|pem|key|crt|credentials)$', fp, re.I):
        block('BLOCKED: Writing to sensitive file: ' + fp + '\nTo update secrets, edit via user config or password manager outside Claude.')

    protected_configs = {
        '.eslintrc', '.eslintrc.js', '.eslintrc.json', 'eslint.config.js', 'eslint.config.mjs',
        '.prettierrc', '.prettierrc.js', '.prettierrc.json', 'prettier.config.js', 'prettier.config.mjs',
        'biome.json', 'biome.jsonc', '.ruff.toml', 'ruff.toml', '.editorconfig',
        'pyproject.toml', 'tsconfig.json', 'jsconfig.json', '.flake8', 'setup.cfg',
    }
    if bn in protected_configs:
        print(f'WARNING: Modifying config file {bn}. Fix the code, not the config.', file=sys.stderr)

    if tn == 'Write' and c:
        line_count = c.count('\n') + 1
        if line_count > 500:
            print(f'WARNING: Creating {line_count}-line file. Consider splitting into smaller files.', file=sys.stderr)

    if bn.upper() == 'TASKS.MD' and 'Claude_Workspace' not in fp:
        ideas = os.path.join(os.path.dirname(fp), 'IDEAS.md')
        if os.path.isfile(ideas):
            block('BLOCKED: This repo already has IDEAS.md. Add tasks there instead of creating TASKS.md.')

    if bn == 'MEMORY.md' and c:
        for line in c.splitlines():
            if re.search(r'feedback_[a-z_]+\.md', line):
                block('BLOCKED: MEMORY.md discipline - never reference individual feedback files by name. Add cross-cutting rules to enforced-rules.md; use ls+grep for navigation. See enforced-rules.md MEMORY.md discipline.')

    if bn.startswith('feedback_') and bn.endswith('.md'):
        if 'ClaudeOnly/memory/feedback' not in fp.replace('\\', '/'):
            block('BLOCKED: Feedback files must go in ClaudeOnly/memory/feedback/ folder. Move ' + bn + ' there.')

    def resulting_size(fp, tn, ti, c):
        if tn == 'Write':
            return len(c.encode('utf-8'))
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                existing = f.read()
            old_string = ti.get('old_string', '')
            new_string = ti.get('new_string', '')
            if ti.get('replace_all'):
                resulting = existing.replace(old_string, new_string)
            else:
                resulting = existing.replace(old_string, new_string, 1)
            return len(resulting.encode('utf-8'))
        except OSError:
            return None

    def check_size_cap(label, soft_cap, hard_cap, hard_msg, soft_msg):
        new_size = resulting_size(fp, tn, ti, c)
        if new_size is not None:
            if new_size > hard_cap:
                block(f'BLOCKED: {label} would be {new_size} bytes (hard cap {hard_cap}). {hard_msg}')
            if new_size > soft_cap:
                print(f'WARNING: {label} would be {new_size} bytes (soft cap {soft_cap}, hard cap {hard_cap}). {soft_msg}', file=sys.stderr)

    if bn == 'enforced-rules.md':
        check_size_cap(
            'enforced-rules.md', 20000, 30000,
            'Trim equal-or-larger text first per feedback_enforced_rules_hygiene.md.',
            'Start trimming now, not at the ceiling. See context-efficiency-tuning.md.',
        )

    fp_norm_slash = fp.replace('\\', '/').lower()
    if bn == 'CLAUDE.md' and fp_norm_slash.rstrip('/').endswith('claude_workspace/claude.md'):
        check_size_cap(
            'CLAUDE.md', 12000, 15000,
            'Move implementation detail to docs/References/DevContext.md; keep only orientation + harm-prevention here.',
            'Auto-loads every session in full - trim toward orientation + harm-prevention only. See feedback_claude_md_scope.md, context-efficiency-tuning.md.',
        )

    if fp.endswith('.md') and c:
        stale = [
            r'\b\d+\b\s+(unit tests?|manifest tests?|routing tests?|assertions?)',
            r'\ball\s+\d+\s+(tests?|assertions?)',
            r'\b\d+/\d+\s+(pass(?:ing)?|green)',
        ]
        for pat in stale:
            if re.search(pat, c, re.I):
                block('BLOCKED: Stale test count in .md file. Use qualitative language: tests must be green / all tests must pass. Exact counts go stale. See enforced-rules.md: Stale numbers in docs.')

    fp_norm = fp.replace('\\', '/').lower()
    if '/claudeonly/roadmap/directives/' in fp_norm and bn.endswith('.md') and bn != 'workspace.md':
        repo_pattern = re.compile(r'githubrepos[/\\]([a-z0-9_\-]+)', re.I)
        repos_mentioned = set()
        for m in repo_pattern.finditer(c):
            repo = m.group(1).lower()
            if repo != 'claude_workspace':
                repos_mentioned.add(repo)
        if repos_mentioned:
            line_count = c.count('\n') + 1
            if line_count > 30:
                block('BLOCKED: Repo directive ' + bn + ' has ' + str(line_count) + ' lines (max 30). Repo: ' + ','.join(repos_mentioned) + '. Move detail to repo IDEAS.md and slim to a pointer. See memory/processes/roadmap-routing.md.')
            has_pointer = any(re.search(r'(?i)^\s*(ideas|see|repo)\s*:', line) for line in c.splitlines())
            if not has_pointer:
                block('BLOCKED: Repo directive ' + bn + ' mentions repo ' + ','.join(repos_mentioned) + ' but lacks Ideas:/See:/Repo: pointer line. See memory/processes/roadmap-routing.md.')
