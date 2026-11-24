import { useEffect, useRef, useState } from 'react'
import {
  Button,
  IconButton,
  Toggletip,
  ToggletipButton,
  ToggletipContent,
  InlineLoading,
  InlineNotification,
  Select,
  SelectItem,
  TextInput,
} from '@carbon/react'
import { Bluetooth, Information, Renew } from '@carbon/icons-react'

export type SensorDevice = {
  id: string
  address: string
  name: string
  transport: 'bluetooth-serial' | 'usb-serial' | 'serial' | 'bluetooth'
  selectable: boolean
  paired: boolean | null
  likely_sensor: boolean
}
export type SensorScan = { devices: SensorDevice[]; warnings: string[]; scope: string }
export type SensorSelection = { address: string; label: string }

type Props = {
  address: string
  onChange: (address: string) => void
  disabled?: boolean
}

export default function SensorPicker({ address, onChange, disabled = false }: Props) {
  const [showManual, setShowManual] = useState(false)
  const [savedLabel, setSavedLabel] = useState('')
  const [devices, setDevices] = useState<SensorDevice[]>([])
  const [scanning, setScanning] = useState(false)
  const [scanned, setScanned] = useState(false)
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState('')
  const edited = useRef(false)
  const mounted = useRef(true)
  const change = useRef(onChange)
  change.current = onChange

  useEffect(() => {
    mounted.current = true
    void window.myocontrol
      .sensorSelection()
      .then((selected) => {
        if (mounted.current && !edited.current && selected) {
          change.current(selected.address)
          setSavedLabel(selected.label)
        }
      })
      .catch(() => {
        if (mounted.current)
          setError('The previous sensor choice could not be restored. Select it again.')
      })
    return () => {
      mounted.current = false
    }
  }, [])

  async function save(next: string, label: string) {
    edited.current = true
    onChange(next)
    setSavedLabel(label)
    setError('')
    try {
      await window.myocontrol.selectSensor({ address: next, label })
    } catch {
      if (mounted.current)
        setError(
          'This sensor can be used now, but the choice could not be saved for the next launch.',
        )
    }
  }

  async function scan() {
    setScanning(true)
    setError('')
    try {
      const result = await window.myocontrol.request<SensorScan>('scan_sensors')
      if (mounted.current) {
        setDevices(result.devices)
        setWarnings(result.warnings)
        setScanned(true)
      }
    } catch {
      if (mounted.current)
        setError(
          'Sensor search failed. Check Bluetooth settings, then rescan or enter a port manually.',
        )
    } finally {
      if (mounted.current) setScanning(false)
    }
  }

  const selected = devices.find((device) => device.selectable && device.address === address)
  return (
    <div className="sensor-picker">
      <div className="sensor-picker__heading">
        <span>Sensor</span>
        <Toggletip align="bottom-start">
          <ToggletipButton label="How to connect BITalino">
            <Information size={16} />
          </ToggletipButton>
          <ToggletipContent>
            <p>Turn on your BITalino and keep it nearby.</p>
            <p>
              Pair it in Windows Bluetooth settings, then rescan and choose its outgoing serial
              port.
            </p>
            <p>
              Your choice is remembered. Discovery finds devices; starting capture checks the
              connection.
            </p>
          </ToggletipContent>
        </Toggletip>
      </div>
      <div className="sensor-picker__row">
        <Select
          id="discovered-sensor"
          labelText="Discovered sensor or serial port"
          hideLabel
          size="md"
          value={selected?.id ?? ''}
          disabled={disabled || scanning}
          onChange={(event) => {
            const device = devices.find((item) => item.id === event.target.value && item.selectable)
            if (device) void save(device.address, device.name)
          }}
        >
          {!selected && (
            <SelectItem
              value=""
              disabled={!address}
              text={address ? `${savedLabel || address} - ${address}` : 'Scan to find a sensor'}
            />
          )}
          {devices.map((device) => (
            <SelectItem
              key={device.id}
              value={device.id}
              disabled={!device.selectable}
              text={
                device.selectable
                  ? `${device.name} - ${device.address}`
                  : `${device.name} (pairing required)`
              }
            />
          ))}
        </Select>
        <IconButton
          label={scanned ? 'Rescan sensors' : 'Scan sensors'}
          kind="ghost"
          size="md"
          type="button"
          align="top"
          disabled={disabled || scanning}
          onClick={() => void scan()}
        >
          <Renew size={20} />
        </IconButton>
        <IconButton
          label="Bluetooth settings"
          kind="ghost"
          size="md"
          type="button"
          align="top"
          disabled={disabled || scanning}
          onClick={() =>
            void window.myocontrol
              .openBluetoothSettings()
              .catch(() =>
                setError('Open Bluetooth settings in your operating system to pair the sensor.'),
              )
          }
        >
          <Bluetooth size={20} />
        </IconButton>
      </div>
      {scanning && <InlineLoading description="Searching for sensors..." />}
      {scanned && devices.length === 0 && (
        <p className="sensor-picker__note" role="status">
          No sensors or serial ports found. Pair the sensor in Bluetooth settings and rescan.
        </p>
      )}
      {scanned && devices.length > 0 && !devices.some((device) => device.selectable) && (
        <p className="sensor-picker__note" role="status">
          Pair your BITalino and enable its outgoing serial port, then rescan.
        </p>
      )}
      {warnings.map((warning) => (
        <p className="sensor-picker__note" key={warning}>
          {warning}
        </p>
      ))}
      {error && (
        <InlineNotification
          kind="warning"
          title="Sensor selection"
          subtitle={error}
          hideCloseButton
        />
      )}
      <Button
        className="sensor-picker__manual-toggle"
        kind="ghost"
        size="sm"
        type="button"
        disabled={disabled || scanning}
        onClick={() => setShowManual((value) => !value)}
        aria-expanded={showManual}
        aria-controls="sensor-manual-entry"
      >
        {showManual ? 'Hide manual entry' : 'Enter port manually'}
      </Button>
      {showManual && (
        <div id="sensor-manual-entry">
          <TextInput
            id="device"
            labelText="Bluetooth serial port or manual address"
            value={address}
            onChange={(event) => {
              edited.current = true
              onChange(event.target.value)
            }}
            onBlur={() => void save(address, address)}
            maxLength={200}
            disabled={disabled || scanning}
            placeholder="COM3 or /dev/cu.BITalino"
          />
        </div>
      )}
    </div>
  )
}
