# Emotiva Remote Interface Description

## 1. SCOPE

### 1.1 Identification
This document describes the Emotiva Network Remote Control protocol.

### 1.2 Purpose
The Emotiva Network Remote Control Protocol is designed to allow control of Emotiva devices over a Local Area Network by third-party remote-control devices.

### 1.3 Document Overview
This document describes the protocol so that third-party remote-control device vendors may implement the protocol.

### 1.4 Version
This is version 3.1 of this document  
R.D. Lesniak  
Embedded Designs, LLC  
July 3, 2024

The previous version of this document was 3.0.1.

Version 3.1 adds:
- Bar notification tags (Big Text and Bar-type Front Panel display information)
- keepAlive and goodbye notifications
- keepAlive interval value to the `<emotivaTransponder>` packet
- Changes transponder operation to always broadcast a transponder packet at startup

### 1.5 Important Changes

As of version 0.4.1 of this document, the remote-control protocol has been updated to Version 2.0. Emotiva devices with later firmware will identify the protocol in use via the `<control><version>` tag in the transponder packet.

Version 2.0 adds:
- New mode notifications (see sections 3.3, 3.4, and 4.2.1)
- Changes the value ranges of the speaker trim-set commands (see section 4.1.1)
- Adds a sequence number on notification packets (see section 2.6)

Version 2.1 adds:
- A model revision number to the Transponder packet (see Section 3.1)

As of version 3.0 of this document, the remote-control protocol has been updated to Version 3.0. Emotiva devices with later firmware will identify the protocol in use via the `<control><version>` tag in the transponder packet.

**IMPORTANT**: In order to maintain support for implementation based on Protocol Version 2.0, Emotiva devices will default to the 2.0 protocol. New implementations should request Version 3.0 via:
- The `<emotivaPing>` transponder request packet (see Section 3.1)
- The `<emotivaSubscribe>` packet (see Section 3.3)
- The `<emotivaUpdate>` packet (see Section 3.6)

**IMPORTANT**: Backwards-compatibility with Protocol Version 2.0 does not include the menu notifications described in Version 2.1 of this document! Menu notifications may not be supported in some 2.0 devices. If they are supported, they will match the Protocol Version 3.0 format.

Prior to Version 3.0, this document referred to notification and update items as "parameters". As of Version 3.0, they are now referred to as "properties".

Version 3.0 changes:
- The format of Notification and Update packets (formerly, each XML element was tagged with the name of the property; in Version 3.0, the XML tag name is now "property", and the property name is identified in a new "name" attribute)
- The format of the Menu Notification packets (see Section 3.4.1 for details)

Version 3.0.1 adds:
- Width and Height speaker trim command and notification tags

Version 3.1 adds:
- Bar notification tags (Big Text and Bar-type Front Panel display information)
- "keepalive" and "goodbye" notifications
- keepAlive interval value to the `<emotivaTransponder>` packet
- Changes transponder operation to always send a transponder packet at startup (equivalent to a "hello" notification)

## 2. Protocol Architecture

### 2.1 Transport Layer
The Emotiva Remote network protocol is based on UDP. Six basic packet transactions are defined:
- Transponder
- Command
- Subscribe
- Unsubscribe
- Notification
- Update

#### 2.1.1 Transponder
The Emotiva device listens for Transponder packets on UDP port number 7000.

The device responds to Transponder packets with a self-identification packet sent on port number 7001.

The self-identification packet specifies:
- The model of Emotiva device (e.g., "XMC-1")
- A revision number for the device
- The user-supplied name of the device (e.g., "living room")
- The UDP port numbers to be used for Control, Notification, and Information packets

**NOTE**: Information packets transactions are currently not implemented and are not covered by this document.

The self-identification packet also specifies the version of the protocol implemented by the device. This document describes Version 1.0., and identifies the changes made to the protocol for Version 2.0.

#### 2.1.2 Commands
The Emotiva device listens for command packets on the UDP port number specified for Control in the Transponder self-identification packet.

Command packets are used to send commands from the remote to the Emotiva device. Commands are similar to those sent by an IR remote control.

The command packet can optionally specify that an acknowledgement packet be returned to the remote. This will be returned to the remote on the UDP command port.

**NOTE**: The acknowledgement is of the receipt of the command. It does not acknowledge execution of the command.

The Emotiva device will generate a notification upon completion of the command, if the remote has subscribed to notifications.

#### 2.1.3 Notifications
The Emotiva device will generate a notification packet whenever one of the monitored conditions changes, whether as a result of:
- A UDP command packet (from any remote)
- An IR command
- A front-panel command
- A menu selection
- An internal status change

The Emotiva device sends notifications to the UDP port number specified for Notification in the Transponder self-identification packet.

In order to receive notifications, the remote device must subscribe to receive them.

#### 2.1.4 Subscriptions
The Emotiva device will report changes in several operational properties. Each property must be subscribed to explicitly – there is no global "get everything" subscription.

For example:
- A remote device might subscribe to notifications of changes in Zone 1 volume level, power state, and input
- Another remote device may only be interested in Zone 2, so it would not subscribe to any Zone 1 notifications

A remote device may subscribe to one or more notifications in a single subscription packet. The Emotiva device listens for Subscription packets on the UDP port number specified for Control in the Transponder self-identification packet.

The Emotiva device sends the Subscription response packet to the UDP port number specified for Control in the Transponder self-identification packet.

Subscription packets may be sent to the Emotiva device at any time. There is no penalty for subscribing to the same notification multiple times – only one notification will be sent regardless of the number of times it is subscribed to.

#### 2.1.5 Unsubscribe
In many cases it is desirable to cancel subscription notifications. For example, if a remote device is monitoring multiple Emotiva devices, it may wish to only receive notifications from one of those devices at any given time. In that case, it can unsubscribe to notifications from the other Emotiva devices.

As with Subscription packets, each notification property must be unsubscribed explicitly. There is no "unsubscribe all" command.

However, a remote device may unsubscribe from one or more notifications in a single subscription packet. The Emotiva device listens for Unsubscribe packets on the UDP port number specified for Control in the Transponder self-identification packet.

The Emotiva device sends the Unsubscribe response packet to the UDP port number specified for Control in the Transponder self-identification packet.

Unsubscribe packets may be sent to the Emotiva device at any time. There is no penalty for unsubscribing from the same notification more than once.

The remote device can re-subscribe at any time.

#### 2.1.6 Update
The remote device can request immediate notification of one or more subscribed properties by transmitting the Update packet. An Update packet contains a list of one or more properties. The remote device must be subscribed to each property it wants an update on.

The Emotiva device listens for Update packets on the UDP port number specified for Control in the Transponder self-identification packet.

Upon receiving an Update packet, the Emotiva device will obtain the current values for each requested property, and it will issue a Notification packet with these values. The Emotiva device sends the update response packet to the UDP port number specified for Control in the Transponder self-identification packet.

The remote device can request an Update at any time.

### 2.2 Data Encoding
The contents of all UDP packets in this protocol are formatted as XML documents. Specific packet formats are detailed in Section 3.

### 2.3 Establishing Communications
The protocol implements a simple scheme for zero-configuration networking. Each Emotiva device listens for UDP packets on Port 7000. When it receives a properly formatted `<emotivaPing>` packet, it responds to the sender's UDP Port 7001 with an XML-formatted response packet.

It is the responsibility of the remote device to discover the Emotiva device(s) on its local network by using UDP Broadcast mode to send the `<emotivaPing>` packet to all Emotiva devices on the network. Active Emotiva Devices will respond with an `<emotivaTransponder>` packet.

Including the "protocol" attribute in the `<emotivaPing>` element will query the Emotiva device for support of the specified protocol version (see Section 3.1).

Protocol Version 3.0 adds to Emotiva Devices the ability to advertise themselves by automatically broadcasting an `<emotivaTransponder>` packet at device startup. The packet is sent to the UDP broadcast address of (255.255.255.255). There is no need to send an `<emotivaPing>` packet in order to receive this advertisement packet.

The `<emotivaTransponder>` response packet contains identification information unique to each Emotiva device on the network. The remote device is expected to transact with each Emotiva device, and it is responsible for remembering the IP addresses of each so that it can send commands and display notification values correctly and coherently.

### 2.4 Commands
Command packets are formatted as XML documents. Each command packet contains a list of one or more command identifiers, along with value for the each command, and an indication of whether or not an acknowledgement is requested for the command identifier.

Supported commands are detailed in Section 3.2. In most cases, the command value will either be zero, or will be in the form of an integer increment or decrement. For example, the "volume" command might have a value of "+1" to indicate that the volume should be raised by 1 dB, or a value of "-1" to indicate that the volume should be lowered by 1 dB.

Other commands require no specific value, and the value should be set to "0". For example, the "power_on" command is not a toggle. It will always execute a power-on regardless of the current state of the Emotiva device. Set the value of the "power_on" and "power_off" commands to "0".

The acknowledgement only acknowledges receipt of a valid command by the Emotiva device. It does not indicate successful and complete execution of the command. Completion is indicated by the transmission of a notification packet (if at least one remote device is subscribed to that notification).

### 2.5 Subscriptions
Subscription, Unsubscribe, and Update packets are formatted as XML documents. Each contains a list of one or more notification properties (for example, current Zone 1 volume, current Zone 1 input, current Zone 1 power status, etc.).

The Emotiva device will respond to Subscription, Unsubscribe and Update packets with a list of the same notification properties. Each valid property will be marked with a status attribute of "ack". Invalid properties will be marked with a status attribute of "nak".

For Subscribe and Update response packets, each valid property will also be marked with a value attribute, containing the current value of the property.

Emotiva devices will default to the Version 2.0 protocol format (as described in Version 2.1 of this document). Including the "protocol" attribute in the `<emotivaSubscribe>` or `<emotivaUpdate>` element will enable the Emotiva device to support the specified protocol version (see Sections 3.3 and 3.6).

### 2.6 Notifications
Notification packets are formatted as XML documents. Each packet contains a list of one or more notification properties (for example, current Zone 1 volume, current Zone 1 input, current Zone 1 power status, etc.).

Each property element will be tagged as "property", and the name of the property will be identified in the "name" attribute. Each property will also be marked with a value attribute, containing the current value of the property. Additional attributes may also be included, depending on the specific property.

The Emotiva device sends Notification packets to the UDP port number specified for Notify in the Transponder self-identification packet.

Notification packets contain a sequence number. The number is incremented for each notification packet generated. The sequence number is passed as an attribute in the top-level XML element.

## 3. Protocol Detailed Design

### 3.1 Transponder Transactions
The remote device initiates a transponder transaction by broadcasting a UDP packet on port 7000. The packet format is as follows:

```xml
<?xml version="1.0" encoding="utf-8"?>
<emotivaPing />
```

Each emotiva device on the network will respond to the remote device on UDP port 7001. The response packet format is as follows:

```xml
<?xml version="1.0"?>
<emotivaTransponder>
  <model>XMC-1</model>
  <revision>2.0</revision>
  <name>Living Room</name>
  <control>
    <version>2.0</version>
    <controlPort>7002</controlPort>
    <notifyPort>7003</notifyPort>
    <infoPort>7004</infoPort>
    <setupPortTCP>7100</setupPortTCP>
    <keepAlive>10000</keepAlive>
  </control>
</emotivaTransponder>
```

Emotiva devices default to Version 2.0 of this protocol. Protocol Version 3.0 adds the ability to query for support of later versions. The query is accomplished by including the "protocol" attribute in the `<emotivaPing>` element. The attribute value indicates the desired protocol version:

```xml
<?xml version="1.0" encoding="utf-8"?>
<emotivaPing protocol="3.0"/>
```

If the device supports the specified protocol version, then this will be reported in the `<emotivaTransponder>` packet. Otherwise, the highest supported protocol version will be reported.

In this example response:
- The Emotiva device is an XMC-1, as reported in the `<model>` tag
- The `<name>` value is "Living Room" (set by the user as the 'friendly name' of the Emotiva device)
- The `<version>` tag reports the version of this protocol being used
- The `<revision>` tag reports the revision of the Emotiva device
- The `<controlPort>` tag contains the UDP port number where the Emotiva device listens for control packets
- The `<notifyPort>` tag contains the UDP port number to which the Emotiva device sends Notification packets
- The `<infoPort>` tag is reserved for future use
- The `<setupPortTCP>` tag contains the TCP port number on which the Emotiva device listens for remote setup connections
- The `<keepAlive>` tag contains a value, in milliseconds, which represents the interval at which the Emotiva Device will send a "keepAlive" notification

### 3.2 Command Transactions
The remote device initiates a command transaction by sending a UDP packet to the Emotiva device's Control port. The packet format consists of one or more command tags. Each command tag takes a "value" attribute, and an optional "ack" attribute.

The "value" attribute is required. The attribute's assigned value is specific to the command. Commands and values are described in Section 4.1.

The "ack" attribute takes a value of either "yes" or "no", depending upon whether or not an acknowledgement packet is requested.

Example of a power-on command transaction:

```xml
<?xml version="1.0" encoding="utf-8"?>
<emotivaControl>
  <power_on value="0" ack="yes" />
</emotivaControl>
```

The Emotiva device responds with:

```xml
<?xml version="1.0"?>
<emotivaAck>
  <power_on status="ack"/>
</emotivaAck>
```

Example of a volume-up command transaction:

```xml
<?xml version="1.0" encoding="utf-8"?>
<emotivaControl>
  <volume value="1" ack="yes" />
</emotivaControl>
```

The Emotiva Device responds with:

```xml
<?xml version="1.0"?>
<emotivaAck>
  <volume status="ack"/>
</emotivaAck>
```

### 3.3 Subscription Transactions
The remote device initiates a Subscription Transaction by sending a UDP packet to the Emotiva device on the UDP `<controlPort>` identified in the `<emotivaTransponder>` packet.

**Note**: Emotiva devices default to Version 2.0 of this protocol. Protocol Version 3.0 adds the ability to request support of later versions. The request is accomplished by including the "protocol" attribute in the `<emotivaSubscription>` element.

Example Subscription packet:

```xml
<?xml version="1.0" encoding="utf-8"?>
<emotivaSubscription protocol="3.0">
  <power />
  <zone2_power />
  <source />
  <mode />
</emotivaSubscription>
```

The Emotiva device responds with:

```xml
<?xml version="1.0" encoding="utf-8"?>
<emotivaSubscription protocol="3.0">
  <property name="power" value="On" visible="true" status="ack"/>
  <property name="zone2_power" value="Off" visible="true" status="ack"/>
  <property name="input_1" value="HDMI 1" visible="true" status="ack"/>
  <property name="input_2" value="HDMI 2" visible="true" status="ack"/>
  <property name="input_3" value="HDMI 3" visible="true" status="ack"/>
  <property name="input_4" value="HDMI 4" visible="true" status="ack"/>
  <property name="input_5" value="HDMI 5" visible="true" status="ack"/>
  <property name="input_6" value="HDMI 6" visible="true" status="ack"/>
  <property name="input_7" value="HDMI 7" visible="true" status="ack"/>
  <property name="input_8" value="HDMI 8" visible="false" status="ack"/>
  <property name="mode_stereo" value="Stereo" visible="true" status="ack"/>
</emotivaSubscription>
```

### 3.4 Notifications
Notification packets are sent automatically by the Emotiva device, whenever subscribed properties change. The remote device does not initiate a notification transaction and must be prepared to receive notification packets at any time.

The notification packet contains a sequence number, which is incremented by the Emotiva device each time a new notification packet is generated.

Example notification packet:

```xml
<?xml version="1.0"?>
<emotivaNotify sequence="6862">
  <property name="tuner_signal" value="Stereo 39dBuV" visible="true"/>
  <property name="tuner_channel" value="FM 106.50MHz" visible="true"/>
  <property name="tuner_program" value="Country" visible="true"/>
  <property name="tuner_RDS" value="Now Playing Old Alabama by Brad Paisley" visible="true"/>
  <property name="audio_input" value="Tuner" visible="true"/>
  <property name="audio_bitstream" value="PCM 2.0" visible="true"/>
  <property name="audio_bits" value="32kHz 24bits" visible="true"/>
  <property name="video_input" value="HDMI 1" visible="true"/>
  <property name="video_format" value="1920x1080P/60" visible="true"/>
  <property name="video_space" value="RGB 8bits " visible="true"/>
</emotivaNotify>
```

#### 3.4.1 Menu Notifications
Menu notifications were added to Protocol Version 2.0; however, they were never implemented in any Emotiva Remote Apps. Version 3.0 implements some changes in the protocol format to simplify App programming.

Example menu notification:

```xml
<?xml version="1.0"?>
<emotivaMenuNotify sequence="2378">
  <row number="0">
    <col number="0" value="" fixed="no" highlight="no" arrow="no"/>
    <col number="1" value="Left Display" fixed="no" highlight="no" arrow="up"/>
    <col number="2" value="Full Status" fixed="no" highlight="no" arrow="no"/>
  </row>
  <!-- Additional rows omitted for brevity -->
</emotivaMenuNotify>
```

#### 3.4.2 Bar Notifications
Bar notifications are added to Protocol Version 3.0. Emotiva devices present temporary front-panel displays consisting of large text or large text combined with a horizontal bar.

Example bar notifications:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<emotivaBarNotify sequence="19">
  <bar max="11.000" min="-96.000" value="-24.000" units="dB" text="Volume" type="bar"/>
</emotivaBarNotify>

<?xml version="1.0" encoding="UTF-8"?>
<emotivaBarNotify sequence="21">
  <bar type="off"/>
</emotivaBarNotify>

<?xml version="1.0" encoding="UTF-8"?>
<emotivaBarNotify sequence="98">
  <bar text="XBox One" type="bigText"/>
</emotivaBarNotify>
```

### 3.5 Unsubscribe Transactions
The remote device initiates a Unsubscribe Transaction by sending a UDP packet to the Emotiva device on the UDP `<controlPort>` identified in the `<emotivaTransponder>` packet.

Example Unsubscribe packet:

```xml
<?xml version="1.0" encoding="utf-8"?>
<emotivaUnsubscribe>
  <power />
  <zone2_power />
  <source />
  <mode />
</emotivaUnsubscribe>
```

The Emotiva device responds with:

```xml
<?xml version="1.0" encoding="utf-8"?>
<emotivaUnsubscribe>
  <power status="ack"/>
  <zone2_power status="ack"/>
  <source status="ack"/>
  <mode status="ack"/>
</emotivaUnsubscribe>
```

### 3.6 Update Transactions
The remote device initiates an UpdateTransaction by sending a UDP packet to the Emotiva device on the UDP `<controlPort>` identified in the `<emotivaTransponder>` packet.

Example Update packet:

```xml
<?xml version="1.0" encoding="utf-8"?>
<emotivaUpdate protocol="3.0">
  <power />
  <source />
  <volume />
  <audio_bitstream />
  <audio_bits />
  <video_input />
  <video_format />
  <video_space />
</emotivaUpdate>
```

The Emotiva device responds with:

```xml
<?xml version="1.0" encoding="utf-8"?>
<emotivaUpdate protocol="3.0">
  <property name="power" value="On" visible="true" status="ack"/>
  <property name="source" value="HDMI 1" visible="true" status="ack"/>
  <property name="volume" value="-40.0" visible="true" status="ack"/>
  <property name="audio_bitstream" value="PCM 0.0" visible="true" status="ack"/>
  <property name="audio_bits" value="48kHz 24bits" visible="true" status="ack"/>
  <property name="video_input" value="HDMI 1" visible="true" status="ack"/>
  <property name="video_format" value="1920x1080P/60" visible="true" status="ack"/>
  <property name="video_space" value="RGB 8bits " visible="true" status="ack"/>
</emotivaUpdate>
```

## 4. Data Description

### 4.1 Command Tags

| Command | Value | Description |
|---------|-------|-------------|
| none | 0 | No command. Ignored. |
| Standby | 0 | Enter standby mode |
| source_tuner | 0 | Set source to Tuner |
| source_1 | 0 | Set source to Input 1 |
| source_2 | 0 | Set source to Input 2 |
| source_3 | 0 | Set source to Input 3 |
| source_4 | 0 | Set source to Input 4 |
| source_5 | 0 | Set source to Input 5 |
| source_6 | 0 | Set source to Input 6 |
| source_7 | 0 | Set source to Input 7 |
| source_8 | 0 | Set source to Input 8 |
| menu | 0 | Enter/Exit menu |
| up | 0 | Menu Up |
| down | 0 | Menu Down |
| left | 0 | Menu Left |
| right | 0 | Menu Right |
| enter | 0 | Menu Enter |
| dim | 0 | Cycle through FP dimness settings |
| mode | +1/-1 | Mode up/down |
| info | 0 | Show Info screen |
| mute | 0 | Zone 1 Mute Toggle |
| mute_on | 0 | Zone 1 Mute on |
| mute_off | 0 | Zone 1 Mute off |
| music | 0 | Select Music preset |
| movie | 0 | Select Movie preset |
| center | +n/-n | Center Volume increment up/down |
| subwoofer | +n/-n | Subwoofer Volume increment up/down |
| surround | +n/-n | Surrounds Volume increment up/down |
| back | +n/-n | Backs Volume increment up/down |
| input | +n/-n | Change Zone 1 Input up/down |
| input_up | 0 | Zone 1 Input selection increment up |
| input_down | 0 | Zone 1 Input selection increment down |
| power_on | 0 | Zone 1 Power On |
| power_off | 0 | Zone 1 Power Off |
| volume | +n/-n | Zone 1 Volume increment up/down |
| set_volume | n | Zone 1 Volume set level -96..11 |
| loudness_on | 0 | Loudness On |
| loudness_off | 0 | Loudness Off |
| loudness | 0 | Toggle Zone 1 Loudness on/off |
| speaker_preset | 0 | Cycle through Speaker Presets |
| mode_up | 0 | Mode increment up |
| mode_down | 0 | Mode increment down |
| bass_up | 0 | Bass level increment up |
| bass_down | 0 | Bass level increment down |
| treble_up | 0 | Treble level increment up |
| treble_down | 0 | Treble level increment down |
| zone2_power | 0 | Toggle Zone 2 Power On/Off |
| zone2_power_off | 0 | Zone 2 Power Off |
| zone2_power_on | 0 | Zone 2 Power On |
| zone2_volume | +n/-n | Zone 2 Volume increment up/down |
| zone2_set_volume | n | Zone 2 Volume set level -96..11 |
| zone2_input | +1/-1 | Change Zone 2 Input up/down |
| zone1_band | 0 | Toggle Tuner Band AM/FM (also changes tuner in Zone 2) |
| band_am | 0 | Set Tuner Band AM (changes tuner in Zone 1 and Zone 2) |
| band_fm | 0 | Set Tuner Band FM (changes tuner in Zone 1 and Zone 2) |
| zone2_mute | 0 | Toggle Zone 2 Mute |
| zone2_mute_off | 0 | Zone 2 Mute Off |
| zone2_mute_on | 0 | Zone 2 Mute On |
| zone2_band | 0 | Not implemented |
| frequency | +1/-1 | Tuner Frequency up/down |
| seek | +1/-1 | Tuner Seek up/down |
| channel | +1/-1 | Tuner Preset Station up/down |
| stereo | 0 | Select mode Stereo |
| direct | 0 | Select mode Direct |
| dolby | 0 | Select mode Dolby |
| dts | 0 | Select mode DTS |
| all_stereo | 0 | Select mode All Stereo |
| auto | 0 | Select mode Auto |
| reference_stereo | 0 | Set Mode to Reference Stereo |
| surround_mode | 0 | Set mode to Surround |
| preset1 | 0 | Select speaker preset 1 |
| preset2 | 0 | Select speaker preset 2 |
| dirac | 0 | Select speaker DIRAC |
| hdmi1 | 0 | Select input HDMI 1 |
| hdmi2 | 0 | Select input HDMI 2 |
| hdmi3 | 0 | Select input HDMI 3 |
| hdmi4 | 0 | Select input HDMI 4 |
| hdmi5 | 0 | Select input HDMI 5 |
| hdmi6 | 0 | Select input HDMI 6 |
| hdmi7 | 0 | Select input HDMI 7 |
| hdmi8 | 0 | Select input HDMI 8 |
| coax1 | 0 | Select input Coax 1 |
| coax2 | 0 | Select input Coax 2 |
| coax3 | 0 | Select input Coax 3 |
| coax4 | 0 | Select input Coax 4 |
| optical1 | 0 | Select input Optical 1 |
| optical2 | 0 | Select input Optical 2 |
| optical3 | 0 | Select input Optical 3 |
| optical4 | 0 | Select input Optical 4 |
| ARC | 0 | Select input ARC |
| usb_stream | 0 | Select input USB stream |
| tuner | 0 | Select input Tuner 1 |
| analog1 | 0 | Select input Analog 1 |
| analog2 | 0 | Select input Analog 2 |
| analog3 | 0 | Select input Analog 3 4 |
| analog4 | 0 | Select input Analog 5 |
| analog5 | 0 | Select input Analog 7.1 |
| analog7.1 | 0 | Select input Analog |
| front_in | 0 | Select input Front |
| center_trim_set | n | Center Volume set level -12.0..+12.0 |
| subwoofer_trim_set | n | Subwoofer Volume set level -12.0..+12.0 |
| surround_trim_set | n | Surrounds Volume set level -12.0..+12.0 |
| back_trim_set | n | Backs Volume set level -12.0..+12.0 |
| width_trim_set | n | Width Volume set level -12.0..+12.0 |
| height_trim_set | n | Height Volume set level -12.0..+12.0 |
| zone2_analog1 | 0 | Select Zone 2 input Analog 1 |
| zone2_analog2 | 0 | Select Zone 2 input Analog 2 |
| zone2_analog3 | 0 | Select Zone 2 input Analog 3 |
| zone2_analog4 | 0 | Select Zone 2 input Analog 4 |
| zone2_analog5 | 0 | Select Zone 2 input Analog 5 |
| zone2_analog71 | 0 | Select Zone 2 input Analog 7.1 |
| zone2_analog8 | 0 | Select Zone 2 input Analog 8 |
| zone2_front_in | 0 | Select Zone 2 input Front |
| zone2_ARC | 0 | Select Zone 2 input ARC |
| zone2_ethernet | 0 | Select Zone 2 input Ethernet |
| zone2_follow_main | 0 | Select Zone 2 input Follow Main |
| zone2_coax1 | 0 | Select Zone 2 input Coax 1 |
| zone2_coax2 | 0 | Select Zone 2 input Coax 2 |
| zone2_coax3 | 0 | Select Zone 2 input Coax 3 |
| zone2_coax4 | 0 | Select Zone 2 input Coax 4 |
| zone2_optical1 | 0 | Select Zone 2 input Optical 1 |
| zone2_optical2 | 0 | Select Zone 2 input Optical 2 |
| zone2_optical3 | 0 | Select Zone 2 input Optical 3 |
| zone2_optical4 | 0 | Select Zone 2 input Optical 4 |
| channel_1 | 0 | Select Tuner Station 1 |
| channel_2 | 0 | Select Tuner Station 2 |
| channel_3 | 0 | Select Tuner Station 3 |
| channel_4 | 0 | Select Tuner Station 4 |
| channel_5 | 0 | Select Tuner Station 5 |
| channel_6 | 0 | Select Tuner Station 6 |
| channel_7 | 0 | Select Tuner Station 7 |
| channel_8 | 0 | Select Tuner Station 8 |
| channel_9 | 0 | Select Tuner Station 9 |
| channel_10 | 0 | Select Tuner Station 10 |
| channel_11 | 0 | Select Tuner Station 11 |
| channel_12 | 0 | Select Tuner Station 12 |
| channel_13 | 0 | Select Tuner Station 13 |
| channel_14 | 0 | Select Tuner Station 14 |
| channel_15 | 0 | Select Tuner Station 15 |
| channel_16 | 0 | Select Tuner Station 16 |
| channel_17 | 0 | Select Tuner Station 17 |
| channel_18 | 0 | Select Tuner Station 18 |
| channel_19 | 0 | Select Tuner Station 19 |
| channel_20 | 0 | Select Tuner Station 20 |

#### 4.1.1 Differences in Protocol Version 2
The following commands have been changed in protocol V2. The ranges of the levels are now -24..+24. This is to allow 0.5dB increments, which maintaining integer values for the levels. The Emotiva Device will automatically divide the values by 2 to get 0.5dB steps in the range -12.0..+12.0

| Command | Value | Description |
|---------|-------|-------------|
| center_trim_set | n | Center Volume set level -24..+24 |
| subwoofer_trim_set | n | Subwoofer Volume set level -24..+24 |
| surround_trim_set | n | Surrounds Volume set level -24..+24 |
| back_trim_set | n | Backs Volume set level -24..+24 |

#### 4.1.2 Differences in Protocol Version 3
The following commands have been added in protocol V3. The ranges of the levels are -24..+24. This is to allow 0.5dB increments, which maintaining integer values for the levels. The Emotiva Device will automatically divide the values by 2 to get 0.5dB steps in the range -12.0..+12.0

| Command | Value | Description |
|---------|-------|-------------|
| width_trim_set | n | Width Volume set level -24..+24 |
| height_trim_set | n | Height Volume set level -24..+24 |

### 4.2 Notification Property Tags
The maximum length of Notification Property strings is 16 characters. An exception is the tuner_program and tuner_RDS properties. In these two cases, the maximum length is 64 characters.

| Property | Description |
|----------|-------------|
| power | Zone 1 power "On"/"Off" |
| source | Zone 1 Input: "HDMI 1", HDMI 2", etc. |
| dim | Front Panel Dimness: "0", "20", "40","60","80","100" |
| mode | Actual Zone 1 Mode: "Stereo", "Direct", "Auto", etc. |
| speaker_preset | Speaker Preset Name |
| center | Center Volume in dB -12.0..12.0 in 0.5 increments |
| subwoofer | Subwoofer Volume in dB -12.0..12.0 in 0.5 increments |
| surround | Surrounds Volume in dB -12.0..12.0 in 0.5 increments |
| back | Backs Volume in dB -12.0..12.0 in 0.5 increments |
| volume | Zone 1 Volume in dB -96..11 increments of 1 |
| loudness | Zone 1 Loudness "On"/"Off" |
| treble | Zone 1 Treble level dB -12.0..12.0 in 0.5 increments |
| bass | Zone 1 Bass level dB -12.0..12.0 in 0.5 increments |
| zone2_power | Zone 2 power "On"/"Off" |
| zone2_volume | Zone 2 Volume in dB -96..11 increments of 1 |
| zone2_input | Zone 2 Input: "HDMI 1", HDMI 2", etc. |
| tuner_band | Tuner Band: "AM" or "FM" |
| tuner_channel | User-assigned station name |
| tuner_signal | Tuner signal quality |
| tuner_program | String: "Country", "Rock", "Classical", etc. |
| tuner_RDS | Tuner RDS string |
| audio_input | Audio Input: "HDMI 1", HDMI 2", etc. |
| audio_bitstream | Audio Bitstream: "PCM 2.0", etc. |
| audio_bits | Audio Bits:"32kHz 24bits", etc. |
| video_input | Video Input: "HDMI 1", HDMI 2", etc. |
| video_format | Video Format: "1920x1080i/60", etc. |
| video_space | Video Space: "YcbCr 8bits", etc. |
| input_1 | User name assigned to Input Button 1 |
| input_2 | User name assigned to Input Button 2 |
| input_3 | User name assigned to Input Button 3 |
| input_4 | User name assigned to Input Button 4 |
| input_5 | User name assigned to Input Button 5 |
| input_6 | User name assigned to Input Button 6 |
| input_7 | User name assigned to Input Button 7 |
| input_8 | User name assigned to Input Button 8 |

#### 4.2.1 Differences in Protocol Version 2
The following notifications have been added in protocol V2:

| Property | Description |
|----------|-------------|
| selected_mode | User-selected Zone 1 mode: "Stereo", "Direct", "Auto", etc. |
| selected_movie_music | Selected movie/music mode: "Movie", or "Music |
| mode_ref_stereo | "Reference Stereo" |
| mode_stereo | "Stereo" |
| mode_music | "Music" |
| mode_movie | "Movie" |
| mode_direct | "Direct" |
| mode_dolby | "Dolby" |
| mode_dts | "DTS" |
| mode_all_stereo | "All Stereo" |
| mode_auto | "Auto" |
| mode_surround | "Surround" |
| menu | Menu display "On"/"Off" |
| menu_update | See section 3.4.1 |

**Note**: 
- "selected_mode" indicates the mode selection made by the user. This may be different than the "mode" notification, as happens when the user selects "Auto". "selected_mode" will continue to return "Auto", while "mode" returns whatever is the actual surround mode on the device.
- "selected_movie_music" returns the current Movie of Music setting of the Emotiva Device. This does not apply to all surround modes. When this is the case, the notification will have the 'visible' attribute set to false.

#### 4.2.2 Differences in Protocol Version 3
The following notifications have been added in protocol V3:

| Property | Description |
|----------|-------------|
| keepAlive | Periodic notification that server is still operating |
| goodbye | Notification that server is shutting down |
| bar_update | See section 3.4.2 |

## 5. Changes

| Version | Changes |
|---------|---------|
| 0.1 | Original |
| 0.2 | Add tuner_band notification |
| 0.3 | Additional command and notification tags. Add "visible" attribute to Notifications and Subscription Notifications |
| 0.4 | Add Zone 1 Bass and Treble notification tags |
| 0.4.1 | Protocol Version 2. Add mode_surround notification. Add selected_mode and selected_movie_music notifications. Correct trims commands |
| 1.0.0 | Add menu and menu_update notifications |
| 2.0 | Add new mode notifications. Change the value ranges of the speaker trim-set commands. Add a sequence number on notification packets |
| 2.1 | Add a model revision number to the Transponder packet |
| 3.0 | Change the format of the `<emotivaNotify>`, `<emotivaUpdate>`, and `<emotivaMenuNotify>` packets. Update the control version to 3.0 |
| 3.0.1 | Add Width and Height speaker trim command and notification tags |
| 3.1 | Add Bar display notifications. Add automatic broadcast of `<emotivaTransponder>` packet at Emotiva Device startup. Add "keepalive" notification interval value to `<emotivaTransponder>` packet. Add "keepalive" and "goodbye" notifications | 