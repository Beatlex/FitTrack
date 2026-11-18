from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator

class MeasurementFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measured_at: datetime | None = None
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    waist_cm: float | None = Field(default=None, gt=0, le=500)
    chest_cm: float | None = Field(default=None, gt=0, le=500)
    hip_cm: float | None = Field(default=None, gt=0, le=500)
    arm_cm: float | None = Field(default=None, gt=0, le=500)
    thigh_cm: float | None = Field(default=None, gt=0, le=500)

    @model_validator(mode="after")
    def require_a_measurement(self):
        values = (self.weight_kg, self.waist_cm, self.chest_cm, self.hip_cm, self.arm_cm, self.thigh_cm)
        if not any(value is not None for value in values):
            raise ValueError("Mindestens ein Körperwert muss angegeben werden.")
        return self

class MeasurementCreate(MeasurementFields):
    pass

class MeasurementUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measured_at: datetime | None = None
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    waist_cm: float | None = Field(default=None, gt=0, le=500)
    chest_cm: float | None = Field(default=None, gt=0, le=500)
    hip_cm: float | None = Field(default=None, gt=0, le=500)
    arm_cm: float | None = Field(default=None, gt=0, le=500)
    thigh_cm: float | None = Field(default=None, gt=0, le=500)
