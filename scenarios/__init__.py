"""Executable assessment fixtures, explicitly labeled offline when used without a provider."""

SCENARIOS = {
    "greenfield": "Build a URL shortener service with URL creation, redirection, analytics and reliability handling.",
    "brownfield": "Enhance the existing URL shortener to support optional URL expiration.",
    "ambiguous": "Make the URL shortener more secure and reliable.",
}

DEMO_CLARIFICATION = (
    "Keep the existing public-destination checks. Limit creation to 20 requests per minute "
    "per direct client. Store aggregate clicks only, no visitor identifiers. "
    "Authentication, password links, and deployment are out of scope for this prototype."
)
