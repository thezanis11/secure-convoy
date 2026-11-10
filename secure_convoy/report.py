"""Exportable figures and an offline replay of actual simulated trajectories."""
import base64
import html
import json
import os
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parents[1] / '.cache/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

NAMES = {'local_acc': 'ACC local', 'trusting_cacc': 'CACC confiant',
         'authenticated_cacc': 'CACC authentifié', 'defended_cacc': 'CACC défensif'}


def embed(path):
    return '<img alt="Résultat expérimental" src="data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode() + '">'


def build_report(trials, summary, manifest, out):
    figures = out / 'figures'
    figures.mkdir(exist_ok=True)
    scenarios = manifest['protocol']['scenarios']
    controllers = manifest['protocol']['controllers']
    heat = np.array([[float(summary.loc[(summary.scenario == s) & (summary.controller == c), 'collision_rate'].iloc[0]) for s in scenarios] for c in controllers])
    fig, ax = plt.subplots(figsize=(12, 4.2), layout='constrained')
    ax.imshow(heat, vmin=0, vmax=1, cmap='YlOrRd', aspect='auto')
    ax.set(xticks=np.arange(len(scenarios)), xticklabels=[s.replace('_', '\n') for s in scenarios],
           yticks=np.arange(len(controllers)), yticklabels=[NAMES[c] for c in controllers],
           title='Fréquence de collision · mêmes 32 graines par scénario et politique')
    for i in range(len(controllers)):
        for j in range(len(scenarios)):
            ax.text(j, i, f'{100*heat[i,j]:.0f} %', ha='center', va='center', color='white' if heat[i,j] > .5 else '#172232')
    fig.savefig(figures / 'collision_matrix.png', dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 4.5), layout='constrained')
    x = np.arange(len(scenarios))
    colors = ['#91aac8', '#ee9868', '#b8a1e9', '#3bcbb0']
    for j, c in enumerate(controllers):
        part = summary.loc[summary.controller == c].set_index('scenario').loc[scenarios]
        ax.plot(x, part.median_min_gap_m, 'o-', label=NAMES[c], color=colors[j])
    ax.axhline(0, color='#b33c3c', ls='--', label='Contact')
    ax.set(xticks=x, xticklabels=[s.replace('_', '\n') for s in scenarios], ylabel='Distance minimale médiane (m)',
           title='Marge physique observée, pas une garantie de sécurité')
    ax.legend(fontsize=8, ncol=3)
    fig.savefig(figures / 'minimum_gaps.png', dpi=160)
    plt.close(fig)
    ablations = pd.read_csv(out / 'ablation_summary.csv')
    fig, ax = plt.subplots(figsize=(10, 4), layout='constrained')
    groups = sorted(ablations.scenario.unique())
    for j, c in enumerate(sorted(ablations.controller.unique())):
        p = ablations.loc[ablations.controller == c].set_index('scenario').loc[groups]
        ax.bar(np.arange(len(groups)) + (j-1)*.24, p.collision_rate, width=.24, label=c.replace('_', ' '))
    ax.set(xticks=np.arange(len(groups)), xticklabels=[s.replace('_', '\n') for s in groups],
           ylim=(0, 1.15), ylabel='Fréquence de collision', title='Ablations · 8 graines par cellule')
    ax.legend(fontsize=8)
    fig.savefig(figures / 'ablations.png', dpi=160)
    plt.close(fig)
    replay = {}
    for path in sorted((out / 'traces').glob('*.csv')):
        scenario, controller, seed = path.stem.split('--')
        frame = pd.read_csv(path)
        all_times = frame.time.drop_duplicates().to_numpy()
        times = np.unique(np.r_[all_times[::4], all_times[-1]])
        sample = frame.loc[frame.time.isin(times)]
        frames = []
        for t, group in sample.groupby('time', sort=True):
            group = group.sort_values('vehicle')
            frames.append(dict(t=round(float(t), 3), x=[round(v, 3) for v in group.position],
                               v=[round(v, 2) for v in group.speed],
                               gap=[None if pd.isna(v) else round(v, 2) for v in group.gap]))
        replay[f'{scenario} / {controller}'] = frames
    rows = ''
    for r in summary.to_dict('records'):
        rows += (f'<tr><td>{r["scenario"]}</td><td>{NAMES[r["controller"]]}</td><td>{r["collisions"]}/{r["trials"]}</td>'
                 f'<td>{100*r["collision_ci_low"]:.1f}–{100*r["collision_ci_high"]:.1f} %</td>'
                 f'<td>{r["median_min_gap_m"]:.2f} m</td><td>{r["median_jerk_rms"]:.2f}</td>'
                 f'<td>{r["attack_packets_accepted"]}</td></tr>')
    options = ''.join(f'<option>{html.escape(key)}</option>' for key in replay)
    nseeds = len(manifest['protocol']['seeds'])
    convergence = pd.read_csv(out/'time_step_study.csv')
    groups = convergence.groupby(['scenario', 'controller', 'seed'])
    changed = sum(group.collision.nunique() > 1 for _, group in groups)
    gap_variation = max(group.min_gap_m.max()-group.min_gap_m.min() for _, group in groups)
    numerical_section = f'<p>Étude du pas de temps : {len(convergence)} essais, {changed} triplets dont la classification de collision change entre 100, 50 et 25 ms. Variation maximale de distance minimale : {gap_variation:.3f} m. <a href="time_step_study.csv">Résultats complets</a>.</p>'
    sumo_section = ''
    if (out/'sumo_experiment.json').exists():
        sumo = json.loads((out/'sumo_experiment.json').read_text(encoding='utf-8'))
        sumo_section = f'<section><div class="eyebrow">04 / Deux moteurs</div><h2>Cohérence en boucle fermée avec SUMO</h2><p>{sumo["runs"]} essais dans {sumo["sumo_version"][1]} : accord sur la présence de collision de {100*sumo["collision_agreement"]:.1f} %, écart absolu maximal de distance minimale de {sumo["max_abs_min_gap_difference"]:.3g} m.</p><p>Les contrôleurs, capteurs et actionneurs sont partagés ; SUMO exécute le déplacement en méthode balistique. Un accord quasi exact est attendu pour ces équations. Cette vérification valide le couplage logiciel, pas une fidélité physique indépendante.</p><p>Les protections automatiques de SUMO sont désactivées pour ne pas masquer les collisions. <a href="sumo_validation.csv">Comparaisons par essai</a> · <a href="sumo_experiment.json">Configuration exacte</a>.</p></section>'
    document = '''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Secure Convoy — étude expérimentale</title><style>
*{box-sizing:border-box}body{margin:0;background:#0b1322;color:#edf3fb;font:16px/1.65 system-ui}main{max-width:1180px;margin:auto;padding:44px 24px}h1{font-size:clamp(40px,6vw,72px);line-height:1.05;letter-spacing:-.05em}h2{font-size:25px}p,li{color:#b5c5db}.eyebrow{color:#4ed8bc;font-size:12px;letter-spacing:.15em;text-transform:uppercase}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card,section{background:#142138;border:1px solid #2c4058;border-radius:13px;padding:22px;margin:22px 0}.card b{display:block;color:#4ed8bc;font-size:30px}.card span{font-size:13px;color:#b5c5db}.notice{border-left:3px solid #ffc180;background:#282335;padding:16px;margin:24px 0}img{width:100%;height:auto;border-radius:8px}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:12px}th,td{text-align:left;padding:12px;border-bottom:1px solid #304258}select,button{background:#0b1322;color:#edf3fb;border:1px solid #4d647e;border-radius:7px;padding:10px;margin:5px}select{max-width:100%}input{width:100%}canvas{width:100%;background:#0b1322;border-radius:10px;display:block}a{color:#4ed8bc}@media(max-width:700px){.cards{grid-template-columns:repeat(2,1fr)}main{padding:24px 12px}section{padding:15px}}
</style></head><body><main><div class="eyebrow">Secure Convoy · contrôle coopératif & sécurité V2X</div><h1>Un message signé<br>peut encore être faux.</h1><p>Étude d'un convoi de sept véhicules : contrôler l'espacement tout en résistant à la falsification, au rejeu et aux défaillances du réseau. Les protections cryptographiques, la cohérence des capteurs et la supervision physique sont évaluées séparément.</p>
<div class="cards"><div class="card"><b>PRIMARY</b><span>simulations principales</span></div><div class="card"><b>SEEDS</b><span>graines appariées par cellule</span></div><div class="card"><b>ABLATIONS</b><span>simulations d'ablation</span></div><div class="card"><b>42 s</b><span>horizon maximal par essai</span></div></div>
<div class="notice">Prototype scientifique longitudinal. Les clés sont publiques et réservées à la démonstration. Aucune sécurité opérationnelle d'un véhicule réel n'est revendiquée. Zéro collision sur un ensemble fini de graines ne prouve pas un risque nul.</div>
<section><div class="eyebrow">01 / Mesures</div><h2>Comparer quatre politiques sur les mêmes conditions</h2>COLLISION_IMAGE GAP_IMAGE<p>ACC local utilise le radar ; CACC confiant accepte les données V2X ; CACC authentifié vérifie signature, séquence et fraîcheur ; CACC défensif ajoute cohérence radar et superviseur d'espacement. Les actionneurs et le bruit physique sont identiques entre politiques.</p><p>Le contrôleur défensif peut augmenter la distance de suivi et dégrader le confort. Il ne faut pas lire une réduction des collisions sans examiner ces coûts.</p></section>
<section><div class="eyebrow">02 / Relecture</div><h2>Rejouer une trajectoire réellement calculée</h2><p>Exemples fixés à la première graine de test, et non choisis selon leur résultat. La relecture s'arrête au premier contact si une collision survient.</p><select id="case">OPTIONS</select><button id="play">Lecture ×3</button><div id="stamp"></div><canvas id="road" width="1100" height="230"></canvas><label for="time">Temps simulé</label><input id="time" type="range" value="0" min="0" step="1"></section>
<section><div class="eyebrow">03 / Attribution des effets</div><h2>Retirer les protections une à une</h2>ABLATION_IMAGE<p>Sans authentification, sans contrôle de cohérence ou sans superviseur : ces variantes séparent les rôles des couches de défense. Elles utilisent un sous-ensemble prescrit de huit graines ; leurs incertitudes sont plus grandes.</p></section>
<section><h2>Résultats détaillés</h2><p>Intervalles à 95 % de Wilson sur la fréquence de collision. Les métriques de confort des essais interrompus par une collision ont un horizon plus court : leur comparaison directe peut être biaisée.</p><div class="scroll"><table><tr><th>Scénario</th><th>Contrôleur</th><th>Collisions</th><th>IC 95 %</th><th>Distance min médiane</th><th>Jerk RMS</th><th>Paquets d'attaque acceptés</th></tr>ROWS</table></div></section>
SUMO_SECTION<section><h2>Protocole, validation et limites</h2>NUMERICAL_SECTION<ul><li>Dynamique longitudinale avec saturation, retard d'actionneur, contrainte de jerk, vitesse non négative et radar bruité. Arrêt au premier contact.</li><li>Messages toutes les 100 ms, file de livraison causale, retard, pertes et coupures. Un attaquant externe n'a pas la clé ; un attaquant interne peut signer des données fausses.</li><li>Graines de test 1000 et suivantes ; grille et paramètres consignés avant la campagne. Les essais de développement utilisent d'autres graines.</li><li>Étude du pas de temps 100/50/25 ms, résultats exportés dans time_step_study.csv. Comparaisons appariées avec bootstrap et empreintes de la recette dans experiment.json.</li><li>Le proxy d'amplification énergétique d'accélération n'est pas une preuve analytique de stabilité en chaîne.</li><li>Le modèle n'inclut pas les manœuvres latérales, l'adhérence détaillée, une vraie pile radio ou la gestion des clés d'une flotte.</li></ul><p>Références : <a href="https://sumo.dlr.de/docs/TraCI/">SUMO / TraCI</a> ; <a href="https://plexe.car2x.org/">Plexe</a>. Équations et hypothèses du contrôleur dans le dépôt.</p></section></main>
<script>const data=REPLAY;const select=document.getElementById('case'),slider=document.getElementById('time'),canvas=document.getElementById('road'),ctx=canvas.getContext('2d');let timer=null;function draw(){const frames=data[select.value];slider.max=frames.length-1;slider.value=Math.min(+slider.value,frames.length-1);const f=frames[+slider.value];document.getElementById('stamp').textContent='t = '+f.t.toFixed(2)+' s · vitesse du leader '+f.v[0].toFixed(1)+' m/s';ctx.clearRect(0,0,1100,230);ctx.strokeStyle='#52647c';ctx.setLineDash([15,12]);ctx.beginPath();ctx.moveTo(20,140);ctx.lineTo(1080,140);ctx.stroke();ctx.setLineDash([]);const scale=950/Math.max(210,f.x[0]-f.x[f.x.length-1]+45);for(let i=f.x.length-1;i>=0;i--){const x=1020-(f.x[0]-f.x[i])*scale;ctx.fillStyle=i===0?'#ffbf7d':'#42d0b3';ctx.fillRect(x-16,90,32,24);ctx.fillStyle='#e8f1ff';ctx.font='13px system-ui';ctx.fillText('V'+i,x-10,75);if(i>0)ctx.fillText(f.gap[i].toFixed(1)+' m',x+25,175);}}select.onchange=()=>{slider.value=0;draw()};slider.oninput=draw;document.getElementById('play').onclick=()=>{if(timer){clearInterval(timer);timer=null;return}timer=setInterval(()=>{if(+slider.value>=+slider.max){clearInterval(timer);timer=null;return}slider.value=+slider.value+1;draw()},67)};draw();</script></body></html>'''
    replacements = {'PRIMARY': str(manifest['primary_runs']), 'SEEDS': str(nseeds), 'ABLATIONS': str(manifest['ablation_runs']),
                    'COLLISION_IMAGE': embed(figures/'collision_matrix.png'), 'GAP_IMAGE': embed(figures/'minimum_gaps.png'),
                    'ABLATION_IMAGE': embed(figures/'ablations.png'), 'OPTIONS': options, 'ROWS': rows,
                    'REPLAY': json.dumps(replay, allow_nan=False), 'SUMO_SECTION': sumo_section, 'NUMERICAL_SECTION': numerical_section}
    # Longest placeholders first to avoid replacing ABLATIONS inside another token.
    for key in sorted(replacements, key=len, reverse=True):
        document = document.replace(key, replacements[key])
    (out / 'index.html').write_text(document, encoding='utf-8')
    lines = ['# Secure Convoy — résultats', '', '| Scénario | Politique | Collisions | Distance min médiane |', '|---|---|---:|---:|']
    for r in summary.to_dict('records'):
        lines.append(f'| {r["scenario"]} | {r["controller"]} | {r["collisions"]}/{r["trials"]} | {r["median_min_gap_m"]:.2f} m |')
    lines += ['', 'Les intervalles de Wilson, coûts de confort, ablations et limites sont détaillés dans le rapport HTML.']
    (out / 'RESULTS_FR.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
