import {
  appleAppSiteAssociation,
  associationResponse,
} from "../../../lib/appLinks";

export function GET() {
  return associationResponse(appleAppSiteAssociation());
}
