# Retrouver et faire évoluer le dépôt

Adresse : https://github.com/thezanis11/secure-convoy

Le code, les tests, les résultats et les exemples de trajectoires sont publiés. Les environnements Python, fichiers temporaires et checkpoints générés restent locaux.

Pour une démonstration sans installation : télécharger le ZIP du dépôt avec **Code → Download ZIP**, extraire les fichiers et ouvrir `reports/index.html`. La relecture utilise des trajectoires déjà calculées ; elle ne lance pas de nouvelle simulation.

Pour modifier le code : ouvrir ce dossier dans l'outil de développement, faire le changement, exécuter les tests puis enregistrer un commit et l'envoyer avec Push. GitHub vérifie les tests, y compris un court couplage SUMO. Les campagnes scientifiques complètes ne sont pas relancées à chaque commit.

Sur cet ordinateur, l'environnement partagé des deux nouveaux projets existe déjà dans le dossier parent `.research-venv`. Depuis le dossier `secure-convoy`, utiliser `..\.research-venv\Scripts\python.exe` pour reprendre les commandes sans réinstaller les bibliothèques. Pour une autre machine, suivre le README.

Avant de mettre un nouveau score sur ton CV, conserver le protocole, les graines, les paramètres et les résultats moins favorables. Le guide d'entretien explique ce qui a été réellement mesuré.
