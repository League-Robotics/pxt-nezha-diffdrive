// identity.ts -- on-robot verification program for sprint 037's runtime
// identity setters (setDeviceRole / setProfile).
//
// Deliberately NOT a boot-time demo. Every setter call is behind a RUN:
// verb so that one flash yields BOTH the baseline (setters never called,
// which must be byte-identical to the pre-sprint firmware) and the
// after-state, from the same image. That also exercises the sprint's
// "a late call MUST succeed" property directly on silicon -- every call
// here lands long after the first banner has already gone out.
//
// Wire vocabulary, RUN:<verb>[:arg...]
//
//   ident:set        setDeviceRole("TESTROLE","testbot") + setProfile("testprofile")
//   ident:ws         whitespace: setDeviceRole("my robot","the bot"), setProfile("the bot")
//                    -- must STRIP to myrobot/thebot/thebot, not reject
//   ident:long       over-length values, must clip rather than corrupt the banner
//   ident:reset      put the baked defaults back, so a session can re-baseline
//
// No motion, no OTOS, no I2C: this program never drives the motors, so
// none of the RUN-fiber motion hazards apply to it.

// Substituted by tools/make_deploy.py in the scratch copy. Same
// obviously-fake placeholders test.ts uses, for the same reason: an
// unsubstituted build must read as visibly wrong, not silently plausible.
const BOOT_VERSION = "00.00"
const BOOT_ROBOT = "unknown"

const BOOT_RADIO_LINK = false
if (BOOT_RADIO_LINK) diffDrive.enableRadioLink()
diffDrive.enableWifiLink()

// The baked values, restated here only so ident:reset can put them back.
// If these drift from protocol.cpp's kRole/kCommonName the reset verb
// reports the wrong thing -- ident:reset is a session convenience, not a
// source of truth about what the firmware was built with.
const BAKED_ROLE = "NEZHA2"
const BAKED_COMMON_NAME = "robot"

diffDrive.onRun("ident", function (arg: number) {
    const which = diffDrive.runArgText(0)

    if (which == "set") {
        diffDrive.setDeviceRole("TESTROLE", "testbot")
        diffDrive.setProfile("testprofile")
        diffDrive.emitLine("IDENT:set role=TESTROLE common=testbot profile=testprofile")

    } else if (which == "ws") {
        // Internal whitespace. The stakeholder chose strip-and-accept
        // over reject, so these must SUCCEED and land stripped.
        diffDrive.setDeviceRole("my robot", "the bot")
        diffDrive.setProfile("the bot")
        diffDrive.emitLine("IDENT:ws expect role=myrobot common=thebot profile=thebot")

    } else if (which == "long") {
        // Past every buffer (roleBuf_/commonNameBuf_ are 24, profileBuf_ 32).
        // The point is that the banner stays a well-formed 5-field line.
        diffDrive.setDeviceRole(
            "ROLEROLEROLEROLEROLEROLEROLEROLEROLE",
            "commoncommoncommoncommoncommoncommon")
        diffDrive.setProfile(
            "profileprofileprofileprofileprofileprofileprofile")
        diffDrive.emitLine("IDENT:long sent role=36 common=36 profile=47")

    } else if (which == "reset") {
        diffDrive.setDeviceRole(BAKED_ROLE, BAKED_COMMON_NAME)
        diffDrive.setProfile(BOOT_ROBOT)
        diffDrive.emitLine("IDENT:reset role=" + BAKED_ROLE
            + " common=" + BAKED_COMMON_NAME
            + " profile=" + BOOT_ROBOT)

    } else {
        diffDrive.emitLine("IDENT:? want set|ws|long|reset")
    }
})

diffDrive.emitLine("IDENT:boot v=" + BOOT_VERSION + " robot=" + BOOT_ROBOT)
