"""One explicit fixed-text/fixed-query compatibility check; no store access."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import time

from ._credentials import Credentials
from ._embedding_plan import load_tokenizer
from ._errors import MycelError
from ._safeguards import InvocationPolicy
from ._voyage import ProviderFailure, VoyageClient


FIXED_TEXT = 'Mycel preserves exact source evidence for dependency review.'
FIXED_QUERY = 'How is exact source evidence preserved?'
LIVE_CHECK_REVISION = 'mycel-embedding-live-v1'


def run_embedding_live_check(settings, *, build, live=False, _client_factory=None,
                             _tokenizer=None, _monotonic=time.monotonic):
    """An on-demand caller must explicitly opt in; ordinary gates never call it.

    The internal client seam is for automatic boundary tests only. A seam-backed
    result is always simulated and cannot establish real live acceptance.
    """
    if live is not True:
        raise MycelError('refused', 'The embedding compatibility check requires explicit live selection.')
    settings.require_valid(require_store=False)
    settings.require_current()
    options = settings.values['embedding']
    tokenizer = _tokenizer or load_tokenizer(options['model'])
    policy = InvocationPolicy('check', action='embedding', live=True)
    real = _client_factory is None and _tokenizer is None
    client = (_client_factory or VoyageClient)(Credentials(settings, policy), policy,
        tokenizer=tokenizer, attempts=1, before_send=settings.require_current)
    results, stopped = [], False
    started = _monotonic()
    try:
        for kind, text in (('document', FIXED_TEXT), ('query', FIXED_QUERY)):
            submitted, planning = tokenizer.counts(text, kind)
            row = {'inputType': kind, 'textSha256': sha256(text.encode('utf-8')).hexdigest(),
                'submittedTokens': submitted, 'planningTokens': planning,
                'providerInputTextTokens': None, 'dimensions': None, 'passed': False,
                'usage': None, 'cost': None, 'attempts': 0}
            tick = _monotonic()
            before_requests = client._requests
            try:
                # The same complete body builder/validation/fixed HTTPS adapter
                # as ordinary embedding; no document prefixes or stored rows.
                response = client._request((text,), options['model'], options['dimensions'], kind)
                row.update(providerInputTextTokens=response.provider_tokens,
                    dimensions=len(response.vectors[0]), usage={'inputTextTokens': response.provider_tokens},
                    attempts=response.requests,
                    passed=(len(response.vectors) == 1 and len(response.vectors[0]) == options['dimensions']
                            and response.provider_tokens == submitted and planning >= submitted))
                if not row['passed']:
                    row['error'] = ({'kind': 'dimension_mismatch', 'message': 'The returned vector dimensions differ from configured dimensions.'}
                        if len(response.vectors) != 1 or len(response.vectors[0]) != options['dimensions'] else
                        {'kind': 'token_count_mismatch', 'message': 'Provider input-text usage differs from the exact submitted-string tokenizer count.'})
            except ProviderFailure as error:
                row['error'] = error.to_dict()
                row['attempts'] = max(0, client._requests - before_requests)
                stopped = True
            except KeyboardInterrupt:
                row['error'] = {'kind': 'cancelled', 'message': 'The live check was stopped by the caller.'}
                row['attempts'] = max(0, client._requests - before_requests)
                stopped = True
            row['elapsedMs'] = max(0.0, (_monotonic() - tick) * 1000)
            results.append(row)
            if stopped or not row['passed']:
                stopped = True
                break
    except KeyboardInterrupt:
        stopped = True
    settings.require_current()
    return {'kind': 'embedding-live', 'reportVersion': 1, 'checkRevision': LIVE_CHECK_REVISION,
        'build': build, 'model': options['model'], 'dimensions': options['dimensions'],
        'recordedAt': datetime.now(timezone.utc).isoformat(), 'live': True,
        'providerExecution': 'production-defaults' if real else 'service-stand-ins',
        'tokenizer': {'repository': tokenizer.catalog.tokenizer_repository,
            'revision': tokenizer.catalog.tokenizer_revision, 'fileSha256': tokenizer.catalog.tokenizer_sha256,
            'librarySha256': tokenizer.library_sha256, 'countingRule': tokenizer.catalog.counting_rule},
        'passed': real and not stopped and len(results) == 2 and all(row['passed'] for row in results),
        'incomplete': stopped or len(results) != 2, 'results': results,
        'elapsedMs': max(0.0, (_monotonic() - started) * 1000), 'cost': None}
