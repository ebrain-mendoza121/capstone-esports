"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import styles from "@/app/mvp.module.css";
import { RuneEntry, RuneMapEntry, frontendMvpClient } from "@/lib/frontendMvpClient";

export default function RuneHistoryPage() {
  const params = useParams<{ puuid: string }>();
  const puuid = Array.isArray(params.puuid) ? params.puuid[0] : params.puuid;

  const [runesMap, setRunesMap] = useState<RuneMapEntry[]>([]);
  const [entries, setEntries] = useState<RuneEntry[]>([]);

  useEffect(() => {
    let mounted = true;

    const loadData = async () => {
      const [mapResponse, historyResponse] = await Promise.all([
        frontendMvpClient.getRunesMap(),
        frontendMvpClient.getPlayerRuneHistory(puuid, 20),
      ]);

      if (!mounted) {
        return;
      }

      setRunesMap(mapResponse);
      setEntries(historyResponse);
    };

    void loadData();

    return () => {
      mounted = false;
    };
  }, [puuid]);

  const mostUsedKeystone = useMemo(() => {
    const counter = new Map<string, number>();
    for (const entry of entries) {
      counter.set(entry.keystone_name, (counter.get(entry.keystone_name) ?? 0) + 1);
    }

    let top: { name: string; count: number } | null = null;
    for (const [name, count] of counter.entries()) {
      if (!top || count > top.count) {
        top = { name, count };
      }
    }

    return top;
  }, [entries]);

  const pathDistribution = useMemo(() => {
    const counter = new Map<string, number>();
    for (const entry of entries) {
      counter.set(entry.primary_style_name, (counter.get(entry.primary_style_name) ?? 0) + 1);
    }

    return Array.from(counter.entries()).map(([name, count]) => ({
      name,
      count,
      percentage: entries.length === 0 ? 0 : Number(((count / entries.length) * 100).toFixed(1)),
    }));
  }, [entries]);

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <header className={styles.hero}>
          <p className={styles.eyebrow}>Frontend MVP · Page 6</p>
          <h1 className={styles.title}>Rune History</h1>
        </header>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Rune Map + History</h2>
              <p className={styles.sectionCopy}>Rune map metadata plus recent player rune history.</p>
            </div>
            <Link className={styles.linkChip} href={`/player/${puuid}`}>
              Back to Dashboard
            </Link>
          </div>

          <div className={styles.inlineList}>
            <span className={styles.badgeNeutral}>Rune map entries: {runesMap.length}</span>
            {mostUsedKeystone ? (
              <span className={styles.badge}>
                Most used keystone: {mostUsedKeystone.name} ({mostUsedKeystone.count} games)
              </span>
            ) : null}
          </div>

          <div className={styles.chartStack}>
            {pathDistribution.map((entry) => (
              <div className={styles.barRow} key={entry.name}>
                <span className={styles.barLabel}>{entry.name}</span>
                <span className={styles.barTrack}>
                  <span className={styles.barFill} style={{ width: `${entry.percentage}%` }} />
                </span>
                <span className={styles.small}>{entry.percentage}%</span>
              </div>
            ))}
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Rune Table</h2>
              <p className={styles.sectionCopy}>Per-match rune choices</p>
            </div>
          </div>

          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Champion</th>
                  <th>Keystone</th>
                  <th>Primary Path</th>
                  <th>Primary Slot 1</th>
                  <th>Primary Slot 2</th>
                  <th>Primary Slot 3</th>
                  <th>Sub Path</th>
                  <th>Sub Slot 1</th>
                  <th>Sub Slot 2</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.match_id}>
                    <td>{entry.champion}</td>
                    <td>{entry.keystone_name}</td>
                    <td>{entry.primary_style_name}</td>
                    <td>{entry.primary_slot1_name}</td>
                    <td>{entry.primary_slot2_name}</td>
                    <td>{entry.primary_slot3_name}</td>
                    <td>{entry.sub_style_name}</td>
                    <td>{entry.sub_slot1_name}</td>
                    <td>{entry.sub_slot2_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}
