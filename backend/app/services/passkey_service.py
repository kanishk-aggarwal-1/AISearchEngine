import json

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from backend.app.config import settings
from backend.app.services.document_store import DocumentStore


class PasskeyService:
    def __init__(self, store: DocumentStore):
        self.store = store

    def begin_registration(self, user_id: str, email: str, display_name: str) -> dict:
        existing = self.store.passkeys_for_user(user_id)
        options = generate_registration_options(
            rp_id=settings.webauthn_rp_id,
            rp_name=settings.webauthn_rp_name,
            user_id=user_id.encode(),
            user_name=email,
            user_display_name=display_name,
            exclude_credentials=[
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(item["credential_id"]))
                for item in existing
            ],
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
        )
        challenge_id = self.store.save_passkey_challenge(
            user_id, bytes_to_base64url(options.challenge), "registration"
        )
        return {"challenge_id": challenge_id, "publicKey": json.loads(options_to_json(options))}

    def finish_registration(self, user_id: str, challenge_id: str, credential: dict, name: str) -> None:
        challenge = self.store.consume_passkey_challenge(challenge_id, "registration")
        if not challenge or challenge["user_id"] != user_id:
            raise ValueError("Invalid or expired passkey challenge")
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge["challenge"]),
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
        )
        transports = credential.get("response", {}).get("transports", [])
        self.store.save_passkey(
            bytes_to_base64url(verified.credential_id), user_id, name,
            bytes_to_base64url(verified.credential_public_key), verified.sign_count, transports,
        )

    def begin_authentication(self, email: str) -> dict:
        user = self.store.passkey_user_by_email(email)
        if not user:
            raise ValueError("No passkeys are registered for this account")
        credentials = self.store.passkeys_for_user(user["user_id"])
        if not credentials:
            raise ValueError("No passkeys are registered for this account")
        options = generate_authentication_options(
            rp_id=settings.webauthn_rp_id,
            allow_credentials=[
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(item["credential_id"]))
                for item in credentials
            ],
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        challenge_id = self.store.save_passkey_challenge(
            user["user_id"], bytes_to_base64url(options.challenge), "authentication"
        )
        return {"challenge_id": challenge_id, "publicKey": json.loads(options_to_json(options))}

    def finish_authentication(self, challenge_id: str, credential: dict):
        challenge = self.store.consume_passkey_challenge(challenge_id, "authentication")
        if not challenge:
            raise ValueError("Invalid or expired passkey challenge")
        stored = self.store.get_passkey(credential.get("id", ""))
        if not stored or stored["user_id"] != challenge["user_id"]:
            raise ValueError("Unknown passkey")
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge["challenge"]),
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            credential_public_key=base64url_to_bytes(stored["public_key"]),
            credential_current_sign_count=int(stored["sign_count"]),
        )
        self.store.update_passkey_counter(stored["credential_id"], verified.new_sign_count)
        return self.store.issue_session(stored["user_id"])
