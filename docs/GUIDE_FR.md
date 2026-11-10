# Présenter et comprendre Secure Convoy

## Démonstration en cinq minutes

1. Ouvrir `reports/index.html` : expliquer pourquoi des véhicules se transmettent leur accélération et leur vitesse.
2. Montrer la matrice de collisions. Comparer attaque externe, attaque interne signée et rejeu.
3. Rejouer `insider_spoof` avec CACC authentifié puis défensif. Expliquer ce que voient réellement les contrôleurs.
4. Montrer les ablations et le coût du superviseur : plus de distance, freinages potentiellement moins confortables.
5. Présenter SUMO sans surinterpréter : il vérifie le couplage avec les mêmes hypothèses, pas le comportement d'une vraie voiture.

## Questions à maîtriser

- **Pourquoi une signature ne suffit-elle pas ?** Elle identifie un détenteur de clé et protège le contenu contre une modification externe. Elle ne garantit pas que les mesures signées sont vraies.
- **Pourquoi conserver un radar local ?** Pour comparer le message à une observation distincte et continuer sans communication. Le radar peut lui-même être bruité ou défaillant.
- **Pourquoi ACC local ne collisionne-t-il pas ici ?** Son espacement est plus conservateur. Cela montre l'utilité d'une référence simple, plutôt que de supposer que la coopération est toujours meilleure.
- **Pourquoi arrêter une collision ?** Après le contact, continuer avec des véhicules indépendants créerait une dynamique physiquement incohérente.
- **Que veut dire 0/32 ?** Aucun échec observé dans ces essais. Ce nombre ne garantit pas une probabilité réelle nulle.
- **Où est l'apprentissage automatique ?** Ce projet étudie des équations de commande et des protocoles, pas une classification entraînée. Le portefeuille comprend aussi CAN Sentinel et Network Watch pour l'apprentissage sur données.

## Contributions personnelles utiles

Ajouter un modèle de radar défaillant ; étudier l'adhérence et les freinages asymétriques ; comparer une autre loi de commande ; introduire une vraie pile de simulation réseau. Fixer le protocole avant les nouveaux résultats et conserver les essais moins favorables.

## Formulation CV après appropriation

« Secure Convoy — Développement assisté d'un banc d'essai Python de commande de convoi et sécurité V2X : authentification, anti-rejeu, cohérence radar, supervision d'espacement, 1 024 simulations appariées, ablations et validation de cohérence en boucle fermée sous SUMO. »

Préciser le recours à l'assistance IA et les parties personnellement comprises, vérifiées ou modifiées. Ne pas le présenter comme un système autonome déployé sur véhicule.
