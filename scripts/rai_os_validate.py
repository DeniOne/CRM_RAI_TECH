# -*- coding: utf-8 -*-
"""Локальный валидатор манифестов RAI OS для CRM RAI (директива RAI-OS-DIR-001).

Проверяет .rai-os/*.yaml против схем из RAI_OS/protocol/schemas/ и выполняет
перекрёстные проверки целостности каталога. Зависимости: только PyYAML (уже
в venv) — внешний jsonschema не требуется, используется встроенный движок
подмножества JSON Schema, покрывающего схемы протокола.

Запуск (из корня репо):
    python scripts/rai_os_validate.py

Расположение схем (в порядке приоритета):
    1) переменная окружения RAI_OS_PROTOCOL_DIR
    2) F:/RAI_ALL_OS/protocol (машина владельца)
    3) ../RAI_ALL_OS/protocol относительно корня репо

CI в репозитории отсутствует; при его появлении команда включается как
обязательная проверка (см. .planning/phases/24-rai-os-adoption/).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RAI_OS_DIR = ROOT / ".rai-os"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------- мини-движок подмножества JSON Schema draft 2020-12 ----------
# Поддерживает: type, required, properties, additionalProperties:false, items,
# enum, const, pattern, minLength, minItems, uniqueItems, format:date,
# $ref:#/$defs/*. Этого достаточно для схем протокола RAI OS.

def _type_ok(value: object, t: str) -> bool:
    return {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "boolean": lambda v: isinstance(v, bool),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    }[t](value)


def validate(instance, schema: dict, defs: dict | None = None, path: str = "$") -> list[str]:
    defs = defs if defs is not None else schema.get("$defs", {})
    errors: list[str] = []

    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            return [f"{path}: неподдерживаемая ссылка $ref {ref}"]
        target = defs.get(ref.split("/", 2)[2])
        if target is None:
            return [f"{path}: сломанная ссылка $ref {ref}"]
        return validate(instance, target, defs, path)

    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(instance, t) for t in types):
            return [f"{path}: ожидался тип {schema['type']}, получен {type(instance).__name__}"]

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: ожидалось константное значение {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: значение {instance!r} вне допустимого набора {schema['enum']}")

    if isinstance(instance, str):
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} не соответствует шаблону {schema['pattern']}")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: короче minLength={schema['minLength']}")
        if schema.get("format") == "date" and not DATE_RE.match(instance):
            errors.append(f"{path}: {instance!r} не является датой YYYY-MM-DD")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: меньше {schema['minItems']} элементов")
        if schema.get("uniqueItems") and len(instance) != len({repr(i) for i in instance}):
            errors.append(f"{path}: элементы не уникальны")
        if "items" in schema:
            for i, item in enumerate(instance):
                errors += validate(item, schema["items"], defs, f"{path}[{i}]")

    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: отсутствует обязательное поле '{req}'")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in props:
                    errors.append(f"{path}: недопустимое поле '{key}' (additionalProperties=false)")
        for key, sub in props.items():
            if key in instance:
                errors += validate(instance[key], sub, defs, f"{path}.{key}")

    return errors


# ---------- загрузка схем ----------

def protocol_dir() -> Path:
    env = os.environ.get("RAI_OS_PROTOCOL_DIR")
    candidates = [
        Path(env) if env else None,
        Path("F:/RAI_ALL_OS/protocol"),
        ROOT.parent / "RAI_ALL_OS" / "protocol",
    ]
    for cand in candidates:
        if cand and (cand / "schemas").is_dir():
            return cand
    tried = ", ".join(str(c) for c in candidates if c)
    print(f"FAIL: каталог схем RAI OS не найден (искали: {tried}). "
          f"Укажите RAI_OS_PROTOCOL_DIR.")
    sys.exit(2)


def load_schema(pdir: Path, name: str) -> dict:
    with open(pdir / "schemas" / name, encoding="utf-8") as f:
        return yaml.safe_load(f)  # схемы — валидный YAML-подсет JSON


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------- перекрёстные проверки целостности ----------

def cross_checks(module: dict, policy: dict, changes: list[dict],
                 waivers: list[dict], acks: list[dict]) -> list[str]:
    errors: list[str] = []
    mid = module["module"]["id"]

    if policy.get("module_id") != mid:
        errors.append(f"policy-lock.module_id={policy.get('module_id')!r} != module.id={mid!r}")

    # governance-поля паспорта указывают на реальные артефакты
    gov = module["governance"]
    lock_path = ROOT / gov["policy_lock"]
    if not lock_path.is_file():
        errors.append(f"governance.policy_lock: файл {gov['policy_lock']} не существует")
    if "rai_os_validate" not in gov["validation_command"]:
        errors.append("governance.validation_command не ссылается на scripts/rai_os_validate.py")
    if gov["status"] == "conformant":
        errors.append("governance.status=conformant без завершённого внедрения — соответствует "
                      "заявлению без доказательств (governance §3)")

    # evidence-пути паспорта существуют
    for ev in module.get("evidence", []):
        if not (ROOT / ev).exists():
            errors.append(f"module.evidence: путь не существует: {ev}")

    # записи каталога принадлежат модулю
    for ch in changes:
        if ch.get("module_id") != mid:
            errors.append(f"change {ch.get('id')}: module_id != {mid}")
        if ch.get("status") == "implemented" and not ch.get("evidence"):
            errors.append(f"change {ch.get('id')}: статус implemented без evidence")
    for w in waivers:
        if w.get("module_id") != mid:
            errors.append(f"waiver {w.get('id')}: module_id != {mid}")

    # в policy-lock.exceptions — только действующие (active) waiver;
    # approved-без-активации — легальный промежуточный статус по решению OS
    listed = set(policy.get("exceptions", []))
    for w in waivers:
        wid = w.get("id", "")
        if wid in listed and w.get("status") in ("proposed", "approved"):
            errors.append(f"policy-lock.exceptions содержит {w.get('status')} waiver {wid} — "
                          f"вносить только после активации (status: active)")
        if wid not in listed and w.get("status") == "active":
            errors.append(f"waiver {wid} active, но отсутствует в policy-lock.exceptions")
        if wid in listed and w.get("status") in ("remediated", "expired", "revoked"):
            errors.append(f"policy-lock.exceptions содержит недействующий waiver {wid} "
                          f"(status: {w.get('status')})")

    # подтверждение директивы ссылается на существующий PLAN
    for ack in acks:
        plan = ROOT / str(ack.get("plan_ref", ""))
        if not plan.is_file():
            errors.append(f"directive-ack {ack.get('directive_id')}: plan_ref не существует: "
                          f"{ack.get('plan_ref')}")

    return errors


# ---------- основная процедура ----------

def main() -> int:
    pdir = protocol_dir()
    print(f"Схемы RAI OS: {pdir}")

    schema_map = [
        ("module.yaml", "module.yaml", "module.schema.json"),
        ("policy-lock.yaml", "policy-lock.yaml", "policy-lock.schema.json"),
    ]
    change_files = sorted((RAI_OS_DIR / "changes").glob("*.yaml"))
    waiver_files = sorted((RAI_OS_DIR / "waivers").glob("*.yaml"))
    ack_files = sorted((RAI_OS_DIR / "directives").glob("*.yaml"))
    schema_map += [(f.name, f, "change.schema.json") for f in change_files]
    schema_map += [(f.name, f, "waiver.schema.json") for f in waiver_files]

    loaded: dict[str, dict] = {}
    failures = 0
    for label, rel, schema_name in schema_map:
        target = rel if isinstance(rel, Path) else RAI_OS_DIR / rel
        if not target.is_file():
            print(f"FAIL {label}: файл отсутствует — {target}")
            failures += 1
            continue
        doc = load_yaml(target)
        schema = load_schema(pdir, schema_name)
        errs = validate(doc, schema)
        loaded[label] = doc
        if errs:
            failures += 1
            for e in errs:
                print(f"FAIL {label}: {e}")
        else:
            print(f"OK   {label} — схема {schema_name}")

    # directive-ack: отдельной схемы в протоколе нет — структурная проверка полей шаблона
    ack_required = ["schema_version", "directive_id", "module_id", "status",
                    "acknowledged_by", "acknowledged_at", "plan_ref", "evidence"]
    acks = []
    for f in ack_files:
        doc = load_yaml(f)
        missing = [k for k in ack_required if k not in doc]
        if missing:
            print(f"FAIL {f.name}: directive-ack без полей: {missing}")
            failures += 1
        else:
            print(f"OK   {f.name} — структура directive-ack (схемой протокола не покрывается)")
            acks.append(doc)

    if "module.yaml" in loaded and "policy-lock.yaml" in loaded:
        for e in cross_checks(loaded["module.yaml"], loaded["policy-lock.yaml"],
                              [loaded[f.name] for f in change_files if f.name in loaded],
                              [loaded[f.name] for f in waiver_files if f.name in loaded],
                              acks):
            print(f"FAIL cross-check: {e}")
            failures += 1

    total = len(schema_map) + len(ack_files)
    print("-" * 60)
    if failures:
        print(f"РЕЗУЛЬТАТ: FAIL ({failures} из {total} артефактов)")
        return 1
    print(f"РЕЗУЛЬТАТ: PASS ({total} артефактов, схемы + перекрёстные проверки)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
