#!/usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats
import os

RESULTS_FILE = 'benchmark_results.csv'
DATASETS = ['25', '50', '75', '100']

# Colori distinti
COLOR_NEO4J = '#e74c3c'   # Rosso
COLOR_CASSANDRA = '#3498db' # Blu

def main():
    df = pd.read_csv(RESULTS_FILE)
    datasets = DATASETS

    for q in ['q1', 'q2', 'q3', 'q4']:
        qdf = df[df['query'] == q].copy()
        qdf['dataset'] = pd.Categorical(qdf['dataset'], categories=datasets, ordered=True)
        qdf = qdf.sort_values('dataset')

        neo = qdf[qdf['dbms'] == 'neo4j']
        cas = qdf[qdf['dbms'] == 'cassandra']
        x = np.arange(len(datasets))
        width = 0.35

        # --- Figura 1: Prima esecuzione ---
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(x - width/2, neo['first_ms'], width, label='Neo4j', color=COLOR_NEO4J, edgecolor='black', linewidth=0.5)
        ax.bar(x + width/2, cas['first_ms'], width, label='Cassandra', color=COLOR_CASSANDRA, edgecolor='black', linewidth=0.5)
        ax.set_xlabel('Dimensione Dataset')
        ax.set_ylabel('Tempo (ms)')
        ax.set_title(f'Query {q.upper()} — Tempo prima esecuzione (cold)')
        ax.set_xticks(x)
        ax.set_xticklabels(['25%', '50%', '75%', '100%'])
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        plt.tight_layout()
        plt.savefig(f'q{q}_first.png', dpi=150)
        plt.close()

        # --- Figura 2: Media 30 esecuzioni con IC 95% ---
        fig, ax = plt.subplots(figsize=(10, 6))
        n = 30
        t_val = stats.t.ppf(0.975, n - 1)

        neo_err = t_val * neo['stdev_ms'] / np.sqrt(n)
        cas_err = t_val * cas['stdev_ms'] / np.sqrt(n)

        ax.bar(x - width/2, neo['avg_ms'], width, yerr=neo_err, label='Neo4j',
               color=COLOR_NEO4J, capsize=5, edgecolor='black', linewidth=0.5)
        ax.bar(x + width/2, cas['avg_ms'], width, yerr=cas_err, label='Cassandra',
               color=COLOR_CASSANDRA, capsize=5, edgecolor='black', linewidth=0.5)
        ax.set_xlabel('Dimensione Dataset')
        ax.set_ylabel('Tempo medio (ms)')
        ax.set_title(f'Query {q.upper()} — Media 30 esecuzioni (warm) con IC 95%')
        ax.set_xticks(x)
        ax.set_xticklabels(['25%', '50%', '75%', '100%'])
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        plt.tight_layout()
        plt.savefig(f'q{q}_avg.png', dpi=150)
        plt.close()

    with pd.ExcelWriter('results.xlsx', engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Risultati', index=False)
    print("Grafici rigenerati con colori migliori.")

if __name__ == '__main__':
    main()
