import { useEffect, useRef, useState } from "react";
import { fetchStream } from "../lib/api";
import type { StreamEvent } from "../types/api";

const TERMINAL_STATUSES = ["confirmed", "failed", "cancelled"];

export function useCampaignStream(campaignId: string | null) {
  const [data, setData] = useState<StreamEvent | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(false);
  const closeRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!campaignId) {
      setData(null);
      setStreamError(null);
      setIsLive(false);
      return;
    }
    setStreamError(null);
    setIsLive(true);
    closeRef.current = fetchStream(`/api/campaigns/${campaignId}/stream`, {
      onData(ev) {
        const event = ev as StreamEvent;
        setData(event);
        if (event.campaign_status && TERMINAL_STATUSES.includes(event.campaign_status)) {
          setIsLive(false);
          closeRef.current?.();
        }
        if (event.error) setStreamError(event.error);
      },
      onError(err) {
        setStreamError(err.message);
        setIsLive(false);
      },
      onEnd() {
        setIsLive(false);
      },
    });
    return () => {
      closeRef.current?.();
      closeRef.current = null;
    };
  }, [campaignId]);

  return { data, streamError, isLive };
}
