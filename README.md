# Edison

Logiciel de montage vidéo simple, réalisé en Python (PySide6) dans le cadre des ressources
R5.A.05 et R5.A.06 du BUT Informatique (IUT de Vannes).

## Installation

Python 3.11 ou plus récent est nécessaire.

```bash
pip install -r requirements.txt
```

FFmpeg n'a pas besoin d'être installé : le paquet `imageio-ffmpeg` fournit l'exécutable,
et `av` (PyAV) embarque les bibliothèques de décodage.

## Lancement

Depuis le dossier du dépôt :

```bash
python -m edison
```

Les projets sont enregistrés par défaut dans `Documents/Edison` (fichiers `.edison`).

## Tests

```bash
python -m pytest
```

Les médias de test (`tests/assets/`) sont courts et légers.

## Utilisation rapide

| Action | Comment |
|---|---|
| Importer des médias | Case « + » de l'onglet Import, ou glisser des fichiers depuis l'explorateur |
| Ajouter un média à la trame | Glisser sa vignette sur une piste, ou double-cliquer dessus |
| Déplacer un clip | Glisser-déposer (même piste ou autre piste du même type) |
| Rogner un clip | Tirer sur son bord gauche ou droit |
| Sélection multiple | Ctrl + clic |
| Couper au curseur | Bouton « Couper » (Ctrl+K) |
| Fusionner | Cliquer sur la jonction entre deux clips collés, puis « Fusionner » (Ctrl+M) |
| Supprimer | Bouton « Supprimer » (Suppr) |
| Annuler / rétablir | Ctrl+Z / Ctrl+Y |
| Lecture / pause | Espace |
| Image précédente / suivante | ← / → |
| Zoom de la trame | Ctrl + molette (la molette seule fait défiler) |
| Effets | Bouton « Effet » (Ctrl+E) ou clic droit « Effet… » sur un clip ; sans sélection, l'effet est ajouté sur la piste d'effets et s'applique à toute l'image |
| Modifier / retirer un effet | Clic droit sur le clip > « Effets appliqués » (double-clic sur un bloc de la piste d'effets) |
| Menu clic droit | Sur un clip : séparer l'audio, effets, dupliquer, volume, fondus, supprimer |
| Supprimer un projet | Bouton corbeille au survol d'une carte de l'accueil, ou Fichier > Supprimer le projet (le fichier va dans la corbeille) |

## Architecture

```
edison/
├── model/          Modèle de données sans Qt (Project → Track → Clip → EffectInstance) et opérations d'édition
├── effects/        Effets en plugins : base.py (Effect, Param, registre), video.py, audio.py
├── media/          Lecture des fichiers : analyse, décodage vidéo (PyAV), décodage audio (FFmpeg)
├── render/         render_frame / mix_audio (utilisés par l'aperçu ET l'export), cache des effets audio, export
├── controller/     Contrôleur du projet (sélection, undo/redo via QUndoStack) et lecteur temps réel
├── ui/             Vues Qt : accueil, onglets Import/Export, zone de rendu, trame
└── assets/         Logo et mascotte
```

- Le modèle ne dépend pas de Qt ; les vues écoutent les signaux du contrôleur.
- Chaque modification de la trame est une fonction pure de `model/editing.py`, enveloppée
  par le contrôleur dans une commande annulable (`QUndoStack`).
- Une seule fonction de rendu, `render_frame(project, t, ...)`, sert à l'aperçu et à l'export :
  ce qui est vu est ce qui est exporté.
- Le rendu de l'aperçu, le mixage audio, les imports et l'export tournent hors du thread de
  l'interface, sur une copie du projet.

## Ajouter un effet

Un effet est une classe décorée par `@register` dans `edison/effects/video.py` (ou `audio.py`).
Ses paramètres sont déclarés avec `Param` : la pop-up des effets génère les réglages toute seule.

```python
@register
class BlackHole(VideoEffect):
    type_id = "black_hole"          # identifiant enregistré dans les projets : ne plus le changer
    label = "Effet trou noir"
    description = "L'image est aspirée vers le centre."
    params = (Param("strength", "Intensité", 50, 0, 100, suffix=" %"),)

    def apply(self, frame, t, values, duration):
        # frame : image RGB uint8 ; t : temps depuis le début du clip ; values["strength"]
        return frame
```

Les tailles doivent être relatives à la largeur de l'image, pour que l'aperçu (image réduite)
et l'export (pleine taille) donnent le même résultat.
