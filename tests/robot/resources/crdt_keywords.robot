*** Settings ***
Documentation     CRDT testing keywords
Library           CrdtLibrary.py
Library           Collections

*** Keywords ***
Create LwwReg
    [Documentation]    Create a new LWW Register CRDT
    [Arguments]    ${value}=${None}    ${node_id}=rover-test
    ${reg}=    Create Lww Reg    ${value}    ${node_id}
    RETURN    ${reg}

Create GCounter
    [Documentation]    Create a new G-Counter CRDT
    [Arguments]    ${node_id}=rover-test
    ${counter}=    Create Gcounter    ${node_id}
    RETURN    ${counter}

Create OrSet
    [Documentation]    Create a new OR-Set CRDT
    [Arguments]    ${node_id}=rover-test
    ${orset}=    Create Orset    ${node_id}
    RETURN    ${orset}

Set Value
    [Documentation]    Set a value on an LWW Register
    [Arguments]    ${reg}    ${value}
    ${reg}=    Lww Reg Set    ${reg}    ${value}
    RETURN    ${reg}

Get Value
    [Documentation]    Read the value from an LWW Register
    [Arguments]    ${reg}
    ${val}=    Lww Reg Get    ${reg}
    RETURN    ${val}

Merge States
    [Documentation]    Merge two CRDT states
    [Arguments]    ${a}    ${b}
    ${merged}=    Lww Reg Merge    ${a}    ${b}
    RETURN    ${merged}

Values Should Be Equal
    [Documentation]    Assert two values are equal
    [Arguments]    ${actual}    ${expected}
    Values Should Be Equal    ${actual}    ${expected}

Values Should Not Be Equal
    [Documentation]    Assert two values are not equal
    [Arguments]    ${actual}    ${expected}
    Values Should Not Be Equal    ${actual}    ${expected}
