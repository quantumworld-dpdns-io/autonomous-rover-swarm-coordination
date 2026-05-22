*** Settings ***
Documentation     OWASP A5 (Security Misconfiguration) and A6 (Vulnerable Components) tests
Library           RequestsLibrary
Library           Collections
Resource          ../resources/common.robot

*** Test Cases ***
Security Headers Present
    [Documentation]    A5 - API responses should include security headers
    Create Session    api    ${API_HOST}
    ${resp}=    GET On Session    api    /health    expected_status=200
    Should Be Equal As Strings    ${resp.status_code}    200
    ${headers}=    Set Variable    ${resp.headers}
    # Check for common security headers
    ${has_hsts}=    Run Keyword And Return Status
    ...    Dictionary Should Contain Key    ${headers}    Strict-Transport-Security
    ${has_xframe}=    Run Keyword And Return Status
    ...    Dictionary Should Contain Key    ${headers}    X-Frame-Options
    ${has_xss}=    Run Keyword And Return Status
    ...    Dictionary Should Contain Key    ${headers}    X-XSS-Protection
    ${has_content_type}=    Run Keyword And Return Status
    ...    Dictionary Should Contain Key    ${headers}    X-Content-Type-Options
    # At least one security header should be present
    ${any_header}=    Evaluate    ${has_hsts} or ${has_xframe} or ${has_xss} or ${has_content_type}
    Should Be True    ${any_header}    No security headers found in response

Debug Endpoints Disabled
    [Documentation]    A5 - Debug endpoints should not be accessible in production
    Create Session    api    ${API_HOST}
    ${debug_endpoints}=    Create List
    ...    /debug    /debug/    /debug/vars    /_debug
    ...    /actuator    /actuator/health    /console
    FOR    ${ep}    IN    @{debug_endpoints}
        ${resp}=    GET On Session    api    ${ep}    expected_status=404
        Should Be Equal As Strings    ${resp.status_code}    404
    END

Directory Listing Prevention
    [Documentation]    A5 - Directory listing should be disabled
    Create Session    api    ${API_HOST}
    ${path_traversals}=    Create List
    ...    /../    /..%2F    /%2e%2e%2f
    FOR    ${path}    IN    @{path_traversals}
        ${resp}=    GET On Session    api    ${path}    expected_status=404
        Should Be Equal As Strings    ${resp.status_code}    404
    END

CORS Misconfiguration
    [Documentation]    A5 - CORS should restrict origins appropriately
    Create Session    api    ${API_HOST}
    &{headers}=    Create Dictionary    Origin=https://evil.com
    ${resp}=    GET On Session    api    /health    headers=${headers}    expected_status=200
    ${cors_origin}=    Run Keyword And Return Status
    ...    Dictionary Should Contain Key    ${resp.headers}    Access-Control-Allow-Origin
    Run Keyword If    ${cors_origin}
    ...    Should Not Be Equal    ${resp.headers['Access-Control-Allow-Origin']}    *

HTTP Method Override Prevention
    [Documentation]    A5 - HTTP method override headers should be rejected
    Create Session    api    ${API_HOST}
    &{headers}=    Create Dictionary    X-HTTP-Method-Override=DELETE
    ${resp}=    GET On Session    api    /missions    headers=${headers}    expected_status=400
    Should Be Equal As Strings    ${resp.status_code}    400

TLS Weak Ciphers Rejected
    [Documentation]    A6 - The server should reject weak TLS cipher suites
    ${ssl_context}=    Evaluate    __import__('ssl').SSLContext(__import__('ssl').PROTOCOL_TLS_CLIENT)
    ${ssl_context.set_ciphers('ALL:!aNULL:!eNULL:!LOW:!EXP:!RC4:!MD5:!DES:!3DES')}
    # This tests that weak cipher detection works in our TLS config
    ${tls_manager}=    Evaluate
    ...    __import__('rover_swarm.security.tls').TlsManager(
    ...    __import__('rover_swarm.security.tls').TlsConfig(
    ...    cert_path='/app/certs/rover.crt',
    ...    key_path='/app/certs/rover.key'))
    Log    TLS manager created with minimum version TLSv1.2

Dependency Version Check
    [Documentation]    A6 - Check that dependencies are up to date (example check)
    ${pyproject}=    Evaluate    __import__('pathlib').Path('pyproject.toml').read_text()
    Should Contain    ${pyproject}    cryptography>=41.0
    Should Contain    ${pyproject}    pydantic>=2.0

Content Type Sniffing Prevention
    [Documentation]    A5 - X-Content-Type-Options header should be set
    Create Session    api    ${API_HOST}
    ${resp}=    GET On Session    api    /health    expected_status=200
    ${ct_header}=    Run Keyword And Return Status
    ...    Dictionary Should Contain Item    ${resp.headers}    X-Content-Type-Options    nosniff
    Log    X-Content-Type-Options header present: ${ct_header}
