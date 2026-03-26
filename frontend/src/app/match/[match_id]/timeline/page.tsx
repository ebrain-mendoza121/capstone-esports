"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import styles from "@/app/mvp.module.css";
import {
  MockApiError,
  TimelineAvailability,
  TimelineEvent,
  TimelineFrame,
  frontendMvpClient,
} from "@/lib/frontendMvpClient";

function formatDuration(milliseconds: number): string {
  const totalSeconds = Math.floor(milliseconds / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export default function TimelinePage() {
  const params = useParams<{ match_id: string }>();
  const matchId = Array.isArray(params.match_id) ? params.match_id[0] : params.match_id;

  const [availability, setAvailability] = useState<TimelineAvailability | null>(null);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const [selectedPuuid, setSelectedPuuid] = useState<string>("");
  const [frames, setFrames] = useState<TimelineFrame[]>([]);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const bootstrap = async () => {
      try {
        const timelineMeta = await frontendMvpClient.getTimelineAvailability(matchId);

        if (!mounted) {
          return;
        }

        setAvailability(timelineMeta);
        setSelectedPuuid(timelineMeta.participant_puuids[0] ?? "");
        setTimelineError(null);

        const eventResponse = await frontendMvpClient.getTimelineEvents(matchId, 30);

        if (!mounted) {
          return;
        }

        setEvents(eventResponse.events);
        setCursor(eventResponse.next_cursor);
      } catch (error) {
        if (!mounted) {
          return;
        }

        if (error instanceof MockApiError && error.status === 404) {
          setTimelineError(error.message);
        } else {
          setTimelineError("Timeline endpoint failed unexpectedly.");
        }
      }
    };

    void bootstrap();

    return () => {
      mounted = false;
    };
  }, [matchId]);

  useEffect(() => {
    if (!selectedPuuid) {
      return;
    }

    let mounted = true;

    const loadFrames = async () => {
      const response = await frontendMvpClient.getTimelineFramesByPuuid(matchId, selectedPuuid);
      if (!mounted) {
        return;
      }

      const sorted = [...response].sort((left, right) => left.frame_timestamp - right.frame_timestamp);
      setFrames(sorted);
    };

    void loadFrames();

    return () => {
      mounted = false;
    };
  }, [matchId, selectedPuuid]);

  const availabilitySummary = useMemo(() => {
    if (!availability) {
      return "";
    }

    return `Frame rows: ${availability.frame_rows} · Event rows: ${availability.event_rows} · Interval: ${availability.frame_interval_ms}ms`;
  }, [availability]);

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <header className={styles.hero}>
          <p className={styles.eyebrow}>Frontend MVP · Page 7</p>
          <h1 className={styles.title}>Timeline View</h1>
        </header>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Timeline Availability</h2>
              <p className={styles.sectionCopy}>Availability check before loading frame and event data.</p>
            </div>
            <Link className={styles.linkChip} href={`/match/${matchId}`}>
              Back to Match Detail
            </Link>
          </div>

          {timelineError ? (
            <div className={styles.notice}>{timelineError}</div>
          ) : availability ? (
            <>
              <div className={styles.inlineList}>
                <span className={styles.badgeNeutral}>{availabilitySummary}</span>
              </div>
              <label className={styles.field} style={{ marginTop: "10px", maxWidth: "280px" }}>
                Focus Player PUUID
                <select
                  className={styles.select}
                  value={selectedPuuid}
                  onChange={(event) => setSelectedPuuid(event.target.value)}
                >
                  {availability.participant_puuids.map((puuid) => (
                    <option key={puuid} value={puuid}>
                      {puuid}
                    </option>
                  ))}
                </select>
              </label>
            </>
          ) : (
            <p className={styles.loading}>Checking timeline availability...</p>
          )}
        </section>

        {timelineError ? null : (
          <>
            <section className={styles.section}>
                <div className={styles.sectionHeader}>
                  <div>
                    <h2 className={styles.sectionTitle}>Player Frame Progression</h2>
                    <p className={styles.sectionCopy}>Frame-by-frame progression for the selected player.</p>
                  </div>
                </div>

              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Timestamp</th>
                      <th>Current Gold</th>
                      <th>Total Gold</th>
                      <th>XP</th>
                      <th>Level</th>
                      <th>Total CS</th>
                      <th>Position</th>
                    </tr>
                  </thead>
                  <tbody>
                    {frames.map((frame) => (
                      <tr key={`${frame.frame_timestamp}-${frame.position_x}`}>
                        <td>{formatDuration(frame.frame_timestamp)}</td>
                        <td>{frame.current_gold.toLocaleString()}</td>
                        <td>{frame.total_gold.toLocaleString()}</td>
                        <td>{frame.xp.toLocaleString()}</td>
                        <td>{frame.level}</td>
                        <td>{frame.minions_killed + frame.jungle_minions_killed}</td>
                        <td>
                          ({frame.position_x.toLocaleString()}, {frame.position_y.toLocaleString()})
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <div>
                  <h2 className={styles.sectionTitle}>Event Stream</h2>
                  <p className={styles.sectionCopy}>Chronological timeline events for this match.</p>
                </div>
                <button
                  className={styles.buttonPrimary}
                  type="button"
                  disabled={cursor === null}
                  onClick={async () => {
                    if (cursor === null) {
                      return;
                    }

                    const response = await frontendMvpClient.getTimelineEvents(matchId, 30, cursor);
                    setEvents((current) => [...current, ...response.events]);
                    setCursor(response.next_cursor);
                  }}
                >
                  {cursor === null ? "No More Events" : "Load More"}
                </button>
              </div>

              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Timestamp</th>
                      <th>Type</th>
                      <th>Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((event) => (
                      <tr key={event.id}>
                        <td>{formatDuration(event.timestamp)}</td>
                        <td>
                          <span className={styles.badge}>{event.type}</span>
                        </td>
                        <td>{event.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
