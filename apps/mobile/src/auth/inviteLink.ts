import { isInviteToken } from "@xcode/shared/auth";

const INVITE_LINK = /^(https:\/\/[^/?#]+)\/invite\/?(?:\?[^#]*)?#([^#]*)$/;

// The link token of an invitation link from XCODE Web, or null for any other link. The token travels in the
// fragment, so it is never sent to a server by the link itself.
export function inviteTokenFrom(
  url: string | null | undefined,
  webUrl: string,
): string | null {
  const match = url && webUrl ? INVITE_LINK.exec(url) : null;
  if (!match) return null;
  const origin = webUrl.replace(/\/+$/, "").toLowerCase();
  if (match[1].toLowerCase() !== origin) return null;
  return isInviteToken(match[2]) ? match[2] : null;
}
