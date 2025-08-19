# Flag Submission

In order to score points for captured flags, the flags are submitted over a simple TCP-based plaintext protocol. That protocol was agreed upon by the organizers of several A/D CTFs in this GitHub discussion.

The following documentation describes the generic, agreed-upon protocol. CTF Gameserver itself uses a more restricted flag format, it will for example never generate non-ASCII flags. For details on how CTF Gameserver creates flags, see flag architecture.
Definitions

1. Whitespace consists of one or more space (ASCII 0x20) and/or tab (ASCII 0x09) characters.
2. Newline is a single \n (ASCII 0x0a) character.
3. Flags are sequences of arbitrary characters, except whitespace and newlines.

# Protocol

The client connects to the server on a TCP port specified by the respective CTF. The server MAY send a welcome banner, consisting of anything except two subsequent newlines. The server MUST indicate that the welcome sequence has finished by sending two subsequent newlines (\n\n).

If a general error with the connection or its configuration renders the server inoperable, it MAY send an arbitrary error message and close the connection before sending the welcome sequence. The error message MUST NOT contain two subsequent newlines.

To submit a flag, the client MUST send the flag followed by a single newline. The server's response MUST consist of:

1. A repetition of the submitted flag
2. Whitespace
3. One of the response codes defined below
4. Optionally: Whitespace, followed by a custom message consisting of any characters except newlines
5. Newline

During a single connection, the client MAY submit an arbitrary number of flags. When the client is finished, it MUST close the TCP connection. The server MAY close the connection on inactivity for a certain amount of time.

The client MAY send flags without waiting for the welcome sequence or responses to previously submitted flags. The server MAY send the responses in an arbitrary order; the connection between flags and responses can be derived from the flag repetition in the response.

# Response Codes

- OK: The flag was valid, has been accepted by the server, and will be considered for scoring.
- DUP: The flag was already submitted before (by the same team).
- OWN: The flag belongs to (i.e. is supposed to be protected by) the submitting team.
- OLD: The flag has expired and cannot be submitted anymore.
- INV: The flag is not valid.
- ERR: The server encountered an internal error. It MAY close the TCP connection. Submission may be retried at a later point.

The server MUST implement OK, INV, and ERR. Other response codes are optional. The client MUST be able to handle all specified response codes. For extensibility, the client SHOULD be able to handle any response codes consisting of uppercase ASCII letters.

# Example

"C:" and "S:" indicate lines sent by the client and server, respectively. Each line includes the terminating newline.

    S: Welcome to Academy CTF flag submission!
    S: Please submit one flag per line.
    S:
    C: FLAG{4578616d706c65}
    S: FLAG{4578616d706c65} OK
    C: 🏴‍☠️
    C: FLAG{🤔🧙‍♂️👻💩🎉}
    S: FLAG{🤔🧙‍♂️👻💩🎉} DUP You already submitted this flag
    S: 🏴‍☠️ INV Bad flag format


# Submission script

    #!/usr/bin/env python3
    """
    Academy CTF submission script.
    """
    
    from pwn import *
    from exploitfarm.models.enums import FlagStatus
    
    context.log_level = "critical"
    
    # Response code mappings to FlagStatus
    RESPONSE_MAPPINGS = {
        "OK": FlagStatus.ok,
        "DUP": FlagStatus.invalid,  # Already submitted
        "OWN": FlagStatus.invalid,  # Own flag
        "OLD": FlagStatus.timeout,  # Expired flag
        "INV": FlagStatus.invalid,  # Invalid flag format
        "ERR": FlagStatus.wait,  # Server error, can retry
    }
    
    
    def _read_welcome_banner(conn, timeout=10):
        """Read welcome banner until double newline"""
        banner_lines = []
        try:
            while True:
                line = conn.recvline(timeout=timeout).decode("utf-8", errors="replace")
                banner_lines.append(line.rstrip("\n"))
    
                # Check for double newline (end of welcome)
                if (
                    len(banner_lines) >= 2
                    and banner_lines[-1] == ""
                    and banner_lines[-2] == ""
                ):
                    break
                elif line.strip() == "":
                    # Single empty line, check if next is also empty
                    next_line = conn.recvline(timeout=timeout).decode(
                        "utf-8", errors="replace"
                    )
                    banner_lines.append(next_line.rstrip("\n"))
                    if next_line.strip() == "":
                        break
        except (EOFError, Exception):
            pass
    
        return banner_lines
    
    
    def _parse_response(response_line):
        """Parse a response line according to FAUST CTF protocol"""
        parts = response_line.strip().split(None, 2)  # Split on whitespace, max 3 parts
    
        if len(parts) < 2:
            return None, FlagStatus.wait, "Invalid response format"
    
        flag = parts[0]
        response_code = parts[1]
        message = parts[2] if len(parts) > 2 else ""
    
        # Map response code to FlagStatus
        flag_status = RESPONSE_MAPPINGS.get(response_code, FlagStatus.wait)
    
        return flag, flag_status, f"{response_code}: {message}".strip(": ")
    
    
    def submit(flags, host="10.32.1.1", port=6666, http_timeout=30, **kwargs):
        """
        Submit flags to FAUST CTF submission server
    
        Args:
            flags: List of flags to submit
            host: Submission server hostname
            port: Submission server port
            http_timeout: Connection timeout (renamed for compatibility with exploitfarm)
            **kwargs: Additional arguments (ignored for compatibility)
    
        Yields:
            Tuple of (flag, FlagStatus, message)
        """
        try:
            # Connect to submission server
            conn = remote(host, port, timeout=http_timeout)
    
            # Read welcome banner
            conn.recvline()
            conn.recvline()
            conn.recvline()
            # Submit each flag
            for flag in flags:
                try:
                    # Send flag with newline
                    conn.sendline(flag.encode("utf-8"))
    
                    # Read response
                    response = conn.recvline(timeout=http_timeout).decode(
                        "utf-8", errors="replace"
                    )
                    # Parse response
                    parsed_flag, status, message = _parse_response(response)
    
                    # Verify flag matches (server should echo the flag)
                    if parsed_flag and parsed_flag != flag:
                        message = f"Flag mismatch: {message}"
    
                    yield flag, status, message
    
                except EOFError:
                    yield flag, FlagStatus.wait, "Connection closed by server"
                    break
                except Exception as e:
                    yield flag, FlagStatus.wait, f"Submission error: {e}"
    
            # Close connection
            conn.close()
    
        except Exception as e:
            # Connection failed, return error for all flags
            for flag in flags:
                yield flag, FlagStatus.wait, f"Connection failed: {e}"

