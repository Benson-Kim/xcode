import { androidAssetLinks, associationResponse } from "../../../lib/appLinks";

export function GET() {
  return associationResponse(androidAssetLinks());
}
