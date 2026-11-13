"""Command line: `embedkit hardware`, `embedkit models list|pull|verify`, `embedkit licenses audit`."""

from __future__ import annotations

import argparse
import sys

from . import EmbedkitError, hardware, licenses, store
from .registry import Registry


def _table(rows: list[list[str]], header: list[str]) -> str:
    widths = [max(len(str(r[i])) for r in [header, *rows]) for i in range(len(header))]
    line = lambda r: "  ".join(str(c).ljust(w) for c, w in zip(r, widths)).rstrip()  # noqa: E731
    return "\n".join([line(header), line(["-" * w for w in widths]), *map(line, rows)])


def cmd_hardware(_a, _reg) -> int:
    p = hardware.probe()
    print(f"Système    : {p.os} {p.os_version} ({p.arch})")
    print(
        f"Processeur : {p.cpu} — {p.physical_cores} cœurs physiques, {p.logical_cores} logiques"
    )
    print(f"AVX2       : {'oui' if p.avx2 else 'non'}")
    print(f"Mémoire    : {p.ram_gb:g} Go")
    print(f"Accélérateurs : {', '.join(p.accelerators) or 'aucun (CPU seul)'}")
    print(f"Niveau recommandé : {p.recommended_tier}")
    return 0


def cmd_list(_a, reg: Registry) -> int:
    if not len(reg):
        print("Aucun modèle déclaré.")
        return 0
    rows = [
        [
            m.id,
            m.task,
            str(m.tier),
            m.runtime,
            f"{m.size_mb:g} Mo",
            licenses.status(m),
            "oui" if store.is_installed(m) else "non",
        ]
        for m in reg
    ]
    print(
        _table(
            rows,
            ["modèle", "tâche", "niveau", "runtime", "taille", "licence", "installé"],
        )
    )
    return 0


def _selected(a, reg: Registry):
    if a.all:
        return list(reg)
    if not a.ids:
        raise EmbedkitError("Indiquez un ou plusieurs modèles, ou --all.")
    return [reg.get(i) for i in a.ids]


def cmd_pull(a, reg: Registry) -> int:
    for m in _selected(a, reg):
        licenses.check(m, allow_noncommercial=a.allow_noncommercial or None)
        path = store.pull(m)
        print(f"✓ {m.id} → {path}")
    return 0


def cmd_verify(a, reg: Registry) -> int:
    models = (
        [m for m in reg if store.is_installed(m)]
        if a.all or not a.ids
        else [reg.get(i) for i in a.ids]
    )
    bad = 0
    for m in models:
        if not store.is_installed(m):
            print(f"✗ {m.id} : non installé")
            bad += 1
        elif store.verify(m):
            print(f"✓ {m.id} : intact")
        else:
            print(
                f"✗ {m.id} : sha256 différent, fichier corrompu (relancez « embedkit models pull {m.id} » après l'avoir supprimé)"
            )
            bad += 1
    if not models:
        print("Aucun modèle installé.")
    return 1 if bad else 0


def cmd_audit(_a, reg: Registry) -> int:
    rows = [list(r) for r in licenses.audit(reg)]
    print(
        _table(rows, ["modèle", "code", "poids", "usage commercial"])
        if rows
        else "Aucun modèle déclaré."
    )
    return 1 if any(r[3] != "commerciale" for r in rows) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="embedkit", description="Gérer les modèles d'IA embarquée."
    )
    ap.add_argument(
        "--models-path",
        action="append",
        default=[],
        help="dossier de manifestes supplémentaire",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser(
        "hardware", help="décrire la machine et le niveau recommandé"
    ).set_defaults(func=cmd_hardware)

    models = sub.add_parser(
        "models", help="lister, télécharger, vérifier les modèles"
    ).add_subparsers(dest="action", required=True)
    models.add_parser(
        "list", help="modèles déclarés et état d'installation"
    ).set_defaults(func=cmd_list)
    for name, func, text in (
        ("pull", cmd_pull, "télécharger"),
        ("verify", cmd_verify, "vérifier l'intégrité"),
    ):
        p = models.add_parser(name, help=text)
        p.add_argument("ids", nargs="*")
        p.add_argument("--all", action="store_true")
        if name == "pull":
            p.add_argument(
                "--allow-noncommercial",
                action="store_true",
                help="accepter un modèle sans licence commerciale",
            )
        p.set_defaults(func=func)

    lic = sub.add_parser("licenses", help="licences des modèles").add_subparsers(
        dest="action", required=True
    )
    lic.add_parser(
        "audit", help="lister les licences ; échoue si un modèle n'est pas commercial"
    ).set_defaults(func=cmd_audit)

    a = ap.parse_args(argv)
    try:
        return a.func(a, Registry(extra_dirs=a.models_path))
    except EmbedkitError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
