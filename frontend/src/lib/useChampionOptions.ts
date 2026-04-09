"use client";

import { useEffect, useState } from "react";
import { listChampionOptions } from "@/lib/insightsApi";

let championOptionsCache: string[] | null = null;

export default function useChampionOptions() {
  const [championOptions, setChampionOptions] = useState<string[]>(championOptionsCache ?? []);
  const [loadingChampionOptions, setLoadingChampionOptions] = useState<boolean>(!championOptionsCache);
  const [championOptionsError, setChampionOptionsError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    if (championOptionsCache) {
      return;
    }

    const loadChampionOptions = async () => {
      setLoadingChampionOptions(true);
      try {
        const options = await listChampionOptions();
        championOptionsCache = options;

        if (mounted) {
          setChampionOptions(options);
          if (options.length === 0) {
            setChampionOptionsError("No champion options are currently available.");
          }
        }
      } catch {
        if (mounted) {
          setChampionOptionsError("Champion options could not be loaded.");
        }
      } finally {
        if (mounted) {
          setLoadingChampionOptions(false);
        }
      }
    };

    void loadChampionOptions();

    return () => {
      mounted = false;
    };
  }, []);

  return {
    championOptions,
    loadingChampionOptions,
    championOptionsError,
  };
}
