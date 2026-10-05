# Edison

Logiciel de montage vidéo simple, en Python (PySide6), réalisé dans le cadre des ressources
R5.A.05 et R5.A.06 du BUT Informatique (IUT de Vannes).

Ce dépôt contient la **base du projet** (sprint S2 « Interface principale ») : toute
l'interface s'ouvre et se navigue, et chaque fonctionnalité du cahier des charges a sa place
dans le code, signalée par un commentaire `TODO(Sx)` qui explique quoi faire.

## Installation et lancement

Python 3.11 ou plus récent.

```bash
pip install -r requirements.txt
python -m edison
```

FFmpeg n'a pas besoin d'être installé : `imageio-ffmpeg` fournit l'exécutable et `av` (PyAV)
les bibliothèques de décodage.

## Structure du projet

```
dev-edison/
├── edison/
│   ├── __main__.py        Point d'entrée (python -m edison)
│   ├── app.py             Création de l'application Qt (thème, police, icône)
│   ├── config.py          Constantes partagées : formats acceptés, tailles, dossiers
│   ├── utils.py           Petites fonctions : format_time, format_size, fit_size
│   │
│   ├── model/             MODÈLE (sans Qt)
│   │   ├── project.py     Project → Track → Clip → EffectInstance, sauvegarde .edison
│   │   └── editing.py     Opérations de la trame : couper, fusionner, déplacer...
│   ├── media/             LECTURE DES FICHIERS (sans Qt)
│   │   ├── probe.py       Analyse d'un fichier à l'import (PyAV)
│   │   ├── video_decoder.py  Image d'une vidéo à un instant donné
│   │   ├── audio.py       Décodage du son
│   │   └── ffmpeg.py      Chemin de l'exécutable FFmpeg
│   ├── effects/           EFFETS EN PLUGINS (sans Qt)
│   │   ├── base.py        Classe Effect, paramètres Param, registre (prêt)
│   │   ├── video.py       Effets vidéo (exemple complet : Couleurs négatives)
│   │   └── audio.py       Effets audio
│   ├── render/            RENDU (sans Qt)
│   │   ├── renderer.py    render_frame / mix_audio : utilisés par l'aperçu ET l'export
│   │   └── exporter.py    Export (formats, qualités, estimation de taille prêts)
│   ├── controller/        CONTRÔLEURS (lien modèle ↔ interface)
│   │   ├── project_controller.py  Projet ouvert, sélection, actions d'édition
│   │   ├── player.py      Lecture (position, play/pause, volume)
│   │   └── recent.py      Projets de l'accueil et « Projets récents »
│   ├── ui/                VUES (Qt)
│   │   ├── main_window.py Fenêtre, en-tête, menu « Fichier »
│   │   ├── home_page.py   Page d'accueil (carrousel de projets)
│   │   ├── editor_page.py Page d'édition : assemble les trois zones ci-dessous
│   │   ├── import_panel.py / export_panel.py   Onglets Import et Export
│   │   ├── preview.py     Zone de rendu, commandes de lecture, plein écran
│   │   ├── timeline.py    Trame : règle, pistes, clips, curseur, barre d'outils
│   │   ├── effects_dialog.py  Pop-up des effets (S5)
│   │   ├── dialogs.py     Petites boîtes : nom du projet, volume
│   │   └── theme.py, icons.py, painting.py, widgets.py   Charte graphique et outils de dessin
│   └── assets/            Logo et mascotte
└── tests/                 Tests pytest (+ médias de test dans tests/assets/)
```

### Comment les parties communiquent

```
 Vue (ui/)  ──appelle──▶  Contrôleur (controller/)  ──appelle──▶  Modèle (model/, media/, render/)
    ▲                            │
    └────── signaux Qt ──────────┘   project_changed, media_changed, selection_changed, message
```

- Le **modèle ne connaît pas Qt** : il se teste sans fenêtre et se copie vers les threads.
- Une **vue ne modifie jamais le modèle elle-même** : elle appelle une méthode du contrôleur, qui
  émet un signal, et la vue se redessine.
- Une modification de la trame = **une fonction pure de `model/editing.py`**, appelée par
  `ProjectController._edit(...)`. Le jour où l'Undo/Redo est codé (S5), il est donc ajouté
  à un seul endroit.
- **Une seule fonction de rendu** (`render/renderer.py`) sert à l'aperçu et à l'export.

## Où coder quoi : les sprints

Chaque tâche est marquée dans le code par `TODO(S2)`, `TODO(S3)`... Pour lister celles d'un sprint :

```bash
git grep -n "TODO(S3)"
```

Les boutons dont la fonction n'existe pas encore affichent « à implémenter (sprint Sx) » au lieu
de planter (`controller.todo(...)`). Supprimez l'appel quand la fonction est codée.

| Sprint | Objectif (cahier des charges) | Fichiers principaux | Tests à activer |
|---|---|---|---|
| **S2** | Import fonctionnel | `media/probe.py`, `ProjectController.import_files` (thread), vignettes dans `ui/import_panel.py` | `test_s2_import.py` |
| **S3** | Modèle, menu Fichier, timeline navigable, curseur | `model/editing.py`, `ui/timeline.py` (dessin des clips, souris, molette, dépôt), `media/video_decoder.py`, `rename` | `test_s3_editing.py` |
| **S4** | `render_frame`, lecteur temps réel, lecture audio | `render/renderer.py`, `controller/player.py`, `media/audio.py`, volume et fondus | `test_s4_render.py` |
| **S5** | Effets (plugins), Undo/Redo | `effects/video.py`, `effects/audio.py`, `ui/effects_dialog.py`, `ProjectController._edit` | `test_s5_effects.py` |
| **S6** | Export, sauvegarde/chargement .edison, tests | `render/exporter.py`, `model/project.py` (JSON), `controller/recent.py`, `ui/export_panel.py` | `test_s6_save_export.py` |

Dans chaque fichier de test `test_sX_...py`, les tests sont déjà écrits : retirez la ligne
`pytestmark = pytest.mark.skip(...)` quand la fonctionnalité est prête. Ils vérifient alors votre code.

### Ajouter un effet (S5)

Une classe décorée par `@register` dans `edison/effects/video.py` (ou `audio.py`) : la pop-up
génère les réglages à partir des `Param`, et les tests de `test_s5_effects.py` la vérifient
automatiquement. Exemple :

```python
@register
class Blur(VideoEffect):
    type_id = "blur"                # enregistré dans les projets : ne plus le changer
    label = "Flou"
    description = "Adoucit l'image."
    params = (Param("strength", "Intensité", 40, 0, 100, suffix=" %"),)

    def apply(self, frame, t, values, duration):
        sigma = values["strength"] / 100 * frame.shape[1] * 0.02   # relatif à la largeur
        return frame if sigma < 0.3 else cv2.GaussianBlur(frame, (0, 0), sigma)
```

## Conventions (cahier des charges)

- Docstrings au format NumPy ; noms et commentaires en anglais dans le code, textes de l'interface en français.
- `snake_case` (fonctions, variables), `PascalCase` (classes), `MAJUSCULES` (constantes).
- Le modèle ne dépend pas de Qt ; une seule fonction de rendu pour l'aperçu et l'export.
- Dépendances figées dans `requirements.txt`.
- Branches : `main` (stable), `develop` (intégration), `feature/nom-court`, `fix/nom-court` ;
  tout passe par une pull request relue ; commits à l'impératif, en anglais.

## Tests

```bash
python -m pytest
```

`tests/test_base.py` et `tests/test_ui.py` testent la base et doivent toujours passer.
Les fichiers `tests/test_sX_*.py` correspondent aux sprints (voir le tableau ci-dessus).
