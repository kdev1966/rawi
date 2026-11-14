import argparse
import os
import sys
import tempfile
import time

from . import project, subtitles
from .analyze import analyze, draw_debug
from .depth import compute_depths, compute_layers
from .render import FORMATS, can_burn_subtitles, render
from .sources import InputError, expand_inputs
from .text import read_page


def _text_recognizer(enabled):
    """embedkit's OCR, or None (disabled, or no model available: the text stays empty)."""
    if not enabled:
        return None
    from embedkit import EmbedkitError
    from embedkit.tasks import TextRecognizer

    try:
        rec = TextRecognizer.load()
    except EmbedkitError as exc:
        print(f"Lecture du texte désactivée : {exc}", file=sys.stderr)
        return None
    if rec.tier == 0:
        print(
            "Lecture du texte désactivée : aucun modèle OCR utilisable.",
            file=sys.stderr,
        )
        return None
    return rec


def _depth_estimator(enabled):
    """embedkit's depth model, or None (disabled or unavailable: no parallax)."""
    if not enabled:
        return None
    from embedkit import EmbedkitError
    from embedkit.tasks import DepthEstimator

    try:
        est = DepthEstimator.load()
    except EmbedkitError as exc:
        print(f"Profondeur désactivée : {exc}", file=sys.stderr)
        return None
    if est.tier == 0:
        print(
            "Profondeur désactivée : aucun modèle de profondeur utilisable.",
            file=sys.stderr,
        )
        return None
    return est


def _inpainter(enabled):
    """embedkit's inpainting model (MI-GAN) for real layers, or None (depth warp only)."""
    if not enabled:
        return None
    from embedkit import EmbedkitError
    from embedkit.tasks import Inpainter

    try:
        inp = Inpainter.load()
    except EmbedkitError as exc:
        print(
            f"Calques désactivés (déformation par la profondeur seule) : {exc}",
            file=sys.stderr,
        )
        return None
    if inp.tier == 0:  # Telea smears large areas: keep the depth warp
        return None
    return inp


def cmd_analyser(a):
    pages = []
    os.makedirs(a.controle, exist_ok=True)
    recognizer = _text_recognizer(a.ocr == "oui")
    estimator = _depth_estimator(a.profondeur == "oui")
    inpainter = _inpainter(estimator is not None and a.calques == "oui")
    calques = os.path.join(os.path.dirname(os.path.abspath(a.sortie)), "calques")
    for img in expand_inputs(a.images, a.dossier_pages, pages=a.pages, dpi=a.dpi):
        page = analyze(img, rtl=a.rtl, detection=a.detection)
        if recognizer is not None:
            read_page(page, recognizer)
        if estimator is not None:
            compute_depths(page, estimator, calques)
        if inpainter is not None:
            compute_layers(page, inpainter, calques)
        pages.append(page)
        dbg = os.path.join(
            a.controle, os.path.splitext(os.path.basename(img))[0] + "_controle.jpg"
        )
        draw_debug(page, dbg)
        nb = sum(len(p["bubbles"]) for p in page["panels"])
        lus = sum(1 for p in page["panels"] for b in p["bubbles"] if b.get("text"))
        texte = f", {lus} textes lus" if recognizer is not None else ""
        print(
            f"✓ {os.path.basename(img)} : {len(page['panels'])} cases, {nb} bulles{texte}  → {dbg}"
        )
    projet = project.new_project(pages, a.rtl)
    project.save(projet, a.sortie)
    print(f"\nProjet enregistré : {a.sortie}")
    print(
        "Vérifiez les images de contrôle, corrigez le JSON si besoin (ordre, durées), puis lancez « rendre »."
    )
    return projet


def cmd_rendre(a, projet=None):
    if projet is None:
        projet = project.load(a.projet)
    os.makedirs(a.dossier, exist_ok=True)
    scale = 0.5 if a.apercu else 1.0
    groupes = [[p] for p in projet["pages"]] if not a.tout else [projet["pages"]]
    for i, pages in enumerate(groupes, 1):
        nom = "episode_complet" if a.tout else f"episode_{i:02d}"
        out = os.path.join(a.dossier, f"{nom}_{a.format.replace(':', 'x')}.mp4")
        t = time.time()
        items = (
            subtitles.cues(
                pages,
                a.fps,
                keep_names=a.garder_noms,
                names=subtitles.speaker_names(projet["pages"]),
            )
            if a.sous_titres != "aucun"
            else []
        )
        srt_path, burn, temporary = None, None, None
        mode = a.sous_titres
        if items and mode in ("incrustes", "les-deux") and not can_burn_subtitles():
            print(
                "Attention : ce FFmpeg ne sait pas incruster de sous-titres (libass absent) ; "
                "fichier .srt écrit à la place.",
                file=sys.stderr,
            )
            mode = "srt"
        if items and mode in ("srt", "les-deux"):
            srt_path = os.path.splitext(out)[0] + ".srt"
            subtitles.write_srt(srt_path, items)
        if items and mode in ("incrustes", "les-deux"):
            if srt_path is None:
                fd, temporary = tempfile.mkstemp(suffix=".srt")
                os.close(fd)
                subtitles.write_srt(temporary, items)
            burn = srt_path or temporary
        try:
            d = render(
                pages,
                out,
                fmt=a.format,
                fps=a.fps,
                scale=scale,
                music=a.musique,
                burn_srt=burn,
            )
        finally:
            if temporary:
                os.remove(temporary)
        print(f"✓ {out}  ({d:.1f} s de vidéo, rendu en {time.time() - t:.0f} s)")
        if a.sous_titres != "aucun":
            if not items:
                print("  (aucun texte de bulle : pas de sous-titres)")
            elif srt_path:
                print(f"  sous-titres : {srt_path} ({len(items)})")
            else:
                print(f"  sous-titres incrustés ({len(items)})")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="rawi", description="Transformer des planches de BD en motion comic."
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def opts_analyse(p):
        p.add_argument(
            "images",
            nargs="+",
            help="planches (jpg/png) ou albums PDF, ex. pages/*.jpg album.pdf",
        )
        p.add_argument(
            "--rtl",
            action="store_true",
            help="lecture de droite à gauche (manga, BD arabe)",
        )
        p.add_argument(
            "--controle", default="controle", help="dossier des images de contrôle"
        )
        p.add_argument(
            "--profondeur",
            default="oui",
            choices=["oui", "non"],
            help="profondeur des cases pour la parallaxe (télécharge le modèle au premier usage)",
        )
        p.add_argument(
            "--calques",
            default="non",
            choices=["oui", "non"],
            help="expérimental : premier plan détaché, décor rebâti par MI-GAN "
            "(la découpe par la profondeur coupe encore les personnages)",
        )
        p.add_argument(
            "--ocr",
            default="oui",
            choices=["oui", "non"],
            help="lire le texte des bulles (télécharge le modèle OCR au premier usage)",
        )
        p.add_argument(
            "--detection",
            default="nouvelle",
            choices=["nouvelle", "v01"],
            help="méthode de détection des cases (v01 : celle de la v0.1)",
        )
        p.add_argument(
            "--pages", help="PDF : pages à prendre, ex. 3-10,12 (par défaut : toutes)"
        )
        p.add_argument(
            "--dpi",
            type=int,
            help="PDF : résolution du rendu (par défaut : celle du scan, sinon 300)",
        )
        p.add_argument(
            "--dossier-pages",
            default="pages",
            help="PDF : dossier où ranger les pages extraites",
        )

    def opts_rendu(p):
        p.add_argument("--dossier", default="videos", help="dossier de sortie")
        p.add_argument("--format", default="9:16", choices=list(FORMATS))
        p.add_argument("--fps", type=int, default=30)
        p.add_argument(
            "--apercu", action="store_true", help="rendu rapide en demi-résolution"
        )
        p.add_argument(
            "--tout",
            action="store_true",
            help="une seule vidéo pour toutes les planches",
        )
        p.add_argument("--musique", help="fichier audio de fond (optionnel)")
        p.add_argument(
            "--sous-titres",
            dest="sous_titres",
            default="srt",
            choices=["aucun", "srt", "incrustes", "les-deux"],
            help="sous-titres tirés du texte des bulles : fichier .srt, incrustés, ou les deux",
        )
        p.add_argument(
            "--garder-noms",
            dest="garder_noms",
            action="store_true",
            help="garder le nom de celui qui parle (« Nom: ») au début des sous-titres",
        )

    p = sub.add_parser("analyser", help="détecter cases, ordre de lecture et bulles")
    opts_analyse(p)
    p.add_argument("-o", "--sortie", default="projet.json")
    p = sub.add_parser("rendre", help="générer les vidéos depuis un projet.json")
    p.add_argument("projet")
    opts_rendu(p)
    p = sub.add_parser("auto", help="analyser + rendre en une commande")
    opts_analyse(p)
    opts_rendu(p)
    p.add_argument("-o", "--sortie", default="projet.json")

    a = ap.parse_args(argv)
    try:
        if a.cmd == "analyser":
            cmd_analyser(a)
        elif a.cmd == "rendre":
            cmd_rendre(a)
        else:
            cmd_rendre(a, cmd_analyser(a))
    except (InputError, project.ProjectError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
