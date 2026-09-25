/**
 * The error tree, mirroring the part of `falaw.errors` the browser side needs.
 * Key values never appear in a message.
 */

export class FalError extends Error {
  constructor(
    message: string,
    readonly status: number | null = null,
  ) {
    super(status !== null ? `${message} (HTTP ${status})` : message);
    this.name = new.target.name;
  }
}

/** An argument cannot be canonicalised into falaw's hashed JSON form.
 *  Deliberately loud: a hashing function that guesses is one that collides. */
export class FalNonCanonicalArgument extends FalError {
  constructor(
    message: string,
    readonly path: string,
  ) {
    super(message);
  }
}

/** A model id (or alias) the catalogue does not know. */
export class UnknownModelError extends FalError {}
