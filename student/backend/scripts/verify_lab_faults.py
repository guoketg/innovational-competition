"""校验 13 个编程实验室关卡的故障注入是否真的能造出一个「坏代码」。

用法（在 student/backend 目录下）：
    python scripts/verify_lab_faults.py

对每道关卡，把 curated_mutation_candidates 产出的每个候选注入到参考答案上，
要求满足三条：

1. 至少有一个候选能命中（否则这道题永远只能走通用兜底，故障与知识点脱钩）；
2. 注入后的代码语法合法（否则学生拿到的是一份编译不过的残骸）；
3. 注入后的代码判题不通过（否则这是「假故障」，学生无从修起）。

第 3 条是关键：一个不改变行为的替换比没有替换更糟——它会让学生对着正确代码
找不存在的 bug。
"""

from __future__ import annotations

import ast
import os
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_SCRIPTS_DIR))
sys.path.insert(0, _SCRIPTS_DIR)

from verify_lab_content import REFERENCE_SOLUTIONS  # noqa: E402


def main() -> int:
    from services.agent_lab_faults import FAULT_PROFILES, curated_mutation_candidates
    from services.agent_lab_specs import lab_language
    from services.judge_service import judge_submission

    missing_profile = sorted(set(REFERENCE_SOLUTIONS) - set(FAULT_PROFILES))
    if missing_profile:
        print("缺少故障画像的关卡：" + ", ".join(missing_profile))
        return 1

    failures: list[str] = []
    for exercise_id in sorted(REFERENCE_SOLUTIONS, key=lambda item: (item[0], item[2])):
        code = REFERENCE_SOLUTIONS[exercise_id]
        candidates = curated_mutation_candidates(exercise_id, code)
        if not candidates:
            failures.append(exercise_id)
            print(f"[MISS] {exercise_id}  没有任何 curated 故障候选命中参考答案")
            continue

        language = lab_language(exercise_id)
        verdicts = []
        for index, (mutated, _meta) in enumerate(candidates):
            label = f"{exercise_id}#{index}"
            result = None
            if language == "python":
                try:
                    ast.parse(mutated)
                except SyntaxError as exc:
                    failures.append(label)
                    verdicts.append(f"#{index}=语法错误({exc.msg})")
                    continue
            else:
                result = judge_submission(exercise_id, mutated)
                if result.get("compile_error"):
                    failures.append(label)
                    verdicts.append(f"#{index}=编译失败({result['compile_error'][:60]})")
                    continue
            if mutated == code:
                failures.append(label)
                verdicts.append(f"#{index}=未改变代码")
                continue
            if result is None:
                result = judge_submission(exercise_id, mutated)
            if result["passed"]:
                failures.append(label)
                verdicts.append(f"#{index}=假故障(仍然全过)")
            else:
                verdicts.append(f"#{index}=有效")

        status = "PASS" if all("有效" in item for item in verdicts) else "FAIL"
        print(f"[{status}] {exercise_id}  {len(candidates)} 个候选  " + "  ".join(verdicts))

    print()
    if failures:
        print(f"共 {len(failures)} 处不达标：" + ", ".join(failures))
        return 1
    print(f"全部 {len(REFERENCE_SOLUTIONS)} 关的 curated 故障注入都能造出真实的坏代码。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
