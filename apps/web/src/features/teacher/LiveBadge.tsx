import { Badge } from "@mantine/core";
import { tt } from "../../i18n/vi";
import { useLive } from "./LiveProvider";

export function LiveBadge() {
  const { status } = useLive();
  const [color, text] =
    status === "live" ? ["green", tt.session.live] : status === "connecting" || status === "reconnecting" ? ["yellow", tt.session.reconnecting] : ["gray", tt.session.offline];
  return (
    <Badge color={color} variant="dot" data-testid="live-status" data-status={status}>
      {text}
    </Badge>
  );
}
