*** Settings ***
Documentation     CRDT unit tests for LWW Register, GCounter, OR-Set, Vector Clock, and serialization
Resource          ../resources/common.robot
Resource          ../resources/crdt_keywords.robot

*** Test Cases ***
LWW Register Set And Get
    [Documentation]    Setting a value on an LWW Register should be retrievable
    ${reg}=    Create Lww Reg    node_id=rover-unit
    ${reg}=    Set Value    ${reg}    hello
    ${val}=    Get Value    ${reg}
    Should Be Equal    ${val}    hello

LWW Register Overwrite
    [Documentation]    Setting a new value should overwrite the old value
    ${reg}=    Create Lww Reg    node_id=rover-unit
    ${reg}=    Set Value    ${reg}    first
    ${reg}=    Set Value    ${reg}    second
    ${val}=    Get Value    ${reg}
    Should Be Equal    ${val}    second

LWW Register Merge
    [Documentation]    Merging two registers should pick the latest timestamp
    ${reg_a}=    Create Lww Reg    value=alpha    node_id=rover-a
    ${reg_b}=    Create Lww Reg    value=beta    node_id=rover-b
    Sleep    0.01s
    ${reg_b}=    Set Value    ${reg_b}    beta-later
    ${merged}=    Merge States    ${reg_a}    ${reg_b}
    ${val}=    Get Value    ${merged}
    Should Be Equal    ${val}    beta-later

GCounter Increment And Value
    [Documentation]    Incrementing a GCounter should increase its value
    ${c}=    Create GCounter    node_id=rover-unit
    ${c}=    Gcounter Increment    ${c}    5
    ${c}=    Gcounter Increment    ${c}    3
    ${val}=    Gcounter Value    ${c}
    Should Be Equal As Integers    ${val}    8

GCounter Merge
    [Documentation]    Merging two GCounter should take the max per node
    ${ca}=    Create GCounter    node_id=rover-a
    ${cb}=    Create GCounter    node_id=rover-b
    ${ca}=    Gcounter Increment    ${ca}    10
    ${cb}=    Gcounter Increment    ${cb}    20
    ${merged}=    Gcounter Merge    ${ca}    ${cb}
    ${val}=    Gcounter Value    ${merged}
    Should Be Equal As Integers    ${val}    30

ORSet Add And Contains
    [Documentation]    Elements added to an OR-Set should be contained
    ${s}=    Create OrSet    node_id=rover-unit
    ${s}=    Orset Add    ${s}    item-1
    ${s}=    Orset Add    ${s}    item-2
    Should Be True    ${s.contains("item-1")}
    Should Be True    ${s.contains("item-2")}

ORSet Remove
    [Documentation]    Removing an element should remove it from the set
    ${s}=    Create OrSet    node_id=rover-unit
    ${s}=    Orset Add    ${s}    item-1
    ${s}=    Orset Add    ${s}    item-2
    ${s}=    Orset Remove    ${s}    item-1
    Should Be False    ${s.contains("item-1")}
    Should Be True    ${s.contains("item-2")}

ORSet Merge
    [Documentation]    Merging two OR-Sets should combine elements
    ${sa}=    Create OrSet    node_id=rover-a
    ${sb}=    Create OrSet    node_id=rover-b
    ${sa}=    Orset Add    ${sa}    from-a
    ${sb}=    Orset Add    ${sb}    from-b
    ${merged}=    Orset Merge    ${sa}    ${sb}
    ${vals}=    Orset Value    ${merged}
    Should Contain    ${vals}    from-a
    Should Contain    ${vals}    from-b

Vector Clock Happens Before
    [Documentation]    Vector clock should correctly detect happens-before relationships
    ${vc_a}=    Create Vector Clock    node_id=node-a
    ${vc_b}=    Create Vector Clock    node_id=node-b
    ${vc_a}=    Vector Clock Tick    ${vc_a}
    ${vc_a}=    Vector Clock Tick    ${vc_a}
    ${vc_b}=    Vector Clock Tick    ${vc_b}
    Should Be True    ${vc_b.happens_before(${vc_a})}
    Should Be False    ${vc_a.happens_before(${vc_b})}

CRDT Serialization Round Trip
    [Documentation]    Serializing and deserializing a CRDT should preserve state
    ${reg}=    Create Lww Reg    value=ser-value    node_id=rover-unit
    ${data}=    Crdt Serialize    ${reg}
    ${restored}=    Crdt Deserialize    ${data}
    Should Be Equal    ${restored.value()}    ser-value

CRDT Binary Round Trip
    [Documentation]    to_binary and from_binary should round-trip correctly
    ${orig}=    Create GCounter    node_id=rover-unit
    ${orig}=    Gcounter Increment    ${orig}    42
    ${bin}=    Evaluate    ${orig}.to_binary()
    ${restored}=    Evaluate    __import__('rover_swarm.crdt.gcounter').GCounter.from_binary(${bin})
    Should Be Equal As Integers    ${restored.value()}    42
