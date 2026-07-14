function decode(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), (char) => char.charCodeAt(0)).buffer;
}

function encode(value: ArrayBuffer): string {
  let binary = "";
  new Uint8Array(value).forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function creationOptions(input: Record<string, any>): PublicKeyCredentialCreationOptions {
  return { ...input, challenge: decode(input.challenge), user: { ...input.user, id: decode(input.user.id) },
    excludeCredentials: (input.excludeCredentials || []).map((item: any) => ({ ...item, id: decode(item.id) })) } as PublicKeyCredentialCreationOptions;
}

export function requestOptions(input: Record<string, any>): PublicKeyCredentialRequestOptions {
  return { ...input, challenge: decode(input.challenge),
    allowCredentials: (input.allowCredentials || []).map((item: any) => ({ ...item, id: decode(item.id) })) } as PublicKeyCredentialRequestOptions;
}

export function credentialJSON(value: Credential): Record<string, unknown> {
  const credential = value as PublicKeyCredential;
  const response = credential.response as AuthenticatorAttestationResponse & AuthenticatorAssertionResponse;
  return { id: credential.id, rawId: encode(credential.rawId), type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
    clientExtensionResults: credential.getClientExtensionResults(), response: {
      clientDataJSON: encode(response.clientDataJSON),
      ...(response.attestationObject ? { attestationObject: encode(response.attestationObject) } : {}),
      ...(response.authenticatorData ? { authenticatorData: encode(response.authenticatorData) } : {}),
      ...(response.signature ? { signature: encode(response.signature) } : {}),
      ...(response.userHandle ? { userHandle: encode(response.userHandle) } : {}),
      transports: "getTransports" in response ? response.getTransports() : [],
    } };
}
