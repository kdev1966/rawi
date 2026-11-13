import argparse, glob, json, os, sys, time
from .analyze import analyze, draw_debug, save
from .render import render, FORMATS


def _expand(paths):
    out = []
    for p in paths:
        out += sorted(glob.glob(p)) or [p]
    return out


def cmd_analyser(a):
    pages = []
    os.makedirs(a.controle, exist_ok=True)
    for img in _expand(a.images):
        page = analyze(img, rtl=a.rtl)
        pages.append(page)
        dbg = os.path.join(a.controle, os.path.splitext(os.path.basename(img))[0] + "_controle.jpg")
        draw_debug(page, dbg)
        nb = sum(len(p["bubbles"]) for p in page["panels"])
        print(f"✓ {os.path.basename(img)} : {len(page['panels'])} cases, {nb} bulles  → {dbg}")
    projet = {"version": 1, "rtl": a.rtl, "pages": pages}
    save(projet, a.sortie)
    print(f"\nProjet enregistré : {a.sortie}")
    print("Vérifiez les images de contrôle, corrigez le JSON si besoin (ordre, durées), puis lancez « rendre ».")
    return projet


def cmd_rendre(a, projet=None):
    if projet is None:
        with open(a.projet, encoding="utf-8") as f:
            projet = json.load(f)
    os.makedirs(a.dossier, exist_ok=True)
    scale = 0.5 if a.apercu else 1.0
    groupes = [[p] for p in projet["pages"]] if not a.tout else [projet["pages"]]
    for i, pages in enumerate(groupes, 1):
        nom = "episode_complet" if a.tout else f"episode_{i:02d}"
        out = os.path.join(a.dossier, f"{nom}_{a.format.replace(':', 'x')}.mp4")
        t = time.time()
        d = render(pages, out, fmt=a.format, fps=a.fps, scale=scale, music=a.musique)
        print(f"✓ {out}  ({d:.1f} s de vidéo, rendu en {time.time() - t:.0f} s)")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rawi", description="Transformer des planches de BD en motion comic.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def opts_analyse(p):
        p.add_argument("images", nargs="+", help="planches (jpg/png), ex. pages/*.jpg")
        p.add_argument("--rtl", action="store_true", help="lecture de droite à gauche (manga, BD arabe)")
        p.add_argument("--controle", default="controle", help="dossier des images de contrôle")

    def opts_rendu(p):
        p.add_argument("--dossier", default="videos", help="dossier de sortie")
        p.add_argument("--format", default="9:16", choices=list(FORMATS))
        p.add_argument("--fps", type=int, default=30)
        p.add_argument("--apercu", action="store_true", help="rendu rapide en demi-résolution")
        p.add_argument("--tout", action="store_true", help="une seule vidéo pour toutes les planches")
        p.add_argument("--musique", help="fichier audio de fond (optionnel)")

    p = sub.add_parser("analyser", help="détecter cases, ordre de lecture et bulles")
    opts_analyse(p); p.add_argument("-o", "--sortie", default="projet.json")
    p = sub.add_parser("rendre", help="générer les vidéos depuis un projet.json")
    p.add_argument("projet"); opts_rendu(p)
    p = sub.add_parser("auto", help="analyser + rendre en une commande")
    opts_analyse(p); opts_rendu(p); p.add_argument("-o", "--sortie", default="projet.json")

    a = ap.parse_args(argv)
    if a.cmd == "analyser":
        cmd_analyser(a)
    elif a.cmd == "rendre":
        cmd_rendre(a)
    else:
        cmd_rendre(a, cmd_analyser(a))


if __name__ == "__main__":
    sys.exit(main())
