import math

#estimate_power_demand()

# \(P_{MW}\) = estimated data center power demand in megawatts
# \(A_{ft^2}\) = data center area in square feet from IM3
# \(D_{W/ft^2}\) = assumed power density, meaning watts required per square foot
# \(10^6\) = converts watts to megawatts (1,000,000)
# IM3 sqft represents facility/campus polygon surface area.
# It is NOT assumed to equal usable floor area or IT floor area.
# Estimate buildings only, using an explicit gross-floor-area assumption.
# \(A_{IM3}\) = IM3 building polygon area in ft²
# \(F_A\) = effective-area factor, converting footprint into estimated gross floor area
# \(D\) = critical IT power density in W/ft² of gross floor area

def estimate_facility_energy(it_energy_mwh, pue):

    if not math.isfinite(it_energy_mwh) or it_energy_mwh < 0:

        raise ValueError("IT energy must be finite and can't be negative")

    if not math.isfinite(pue) or pue <1:

        raise ValueError("PUE has to be finite and 1 or above")



    return it_energy_mwh * pue

facilityenergy= estimate_facility_energy(it_energy_mwh=10000, pue=1.2)


def estimate_power_demand(im3_areasqft, effective_areafactor, power_density_perft2, site_type='building'):

    if site_type != 'building':
        raise ValueError("Power estimation only supports building footprints")

    if not math.isfinite(im3_areasqft) or im3_areasqft<= 0 :
        raise ValueError("IM3 area has to be a positive finite number")
           
    if not math.isfinite(effective_areafactor) or effective_areafactor<=0:
        raise ValueError("Effective area factor has to be a positive finite number")
    
    if not math.isfinite(power_density_perft2) or power_density_perft2<=0:
        raise ValueError("Power density has to be a positive finite number")
    
    
    effective_area= (im3_areasqft*effective_areafactor)
    
    power_watts= (effective_area* power_density_perft2)
    
    return power_watts/1000000
    
    




#IM3 gives A 
#D and U are scenario assumptions; source citations still need verification




#estimate_annual_energy()
# \(E_{annual}\) = estimated annual electricity use in MWh/year
# \(P_{MW}\) = estimated power demand in megawatts
# \(8760\) = number of hours in one year
# \(U\) = utilization/load factor, from 0 to 1
# This simple load-factor calculation is separate from the idle-power model.
# Don't pass average IT power here; its utilization is already included.


def estimate_annual_energy(power_mw, utilization):

    hours_year=8760

    if not math.isfinite(power_mw) or power_mw<0:

         raise ValueError("Power demand must be finite and can't be negative")

    if not 0<= utilization <=1:

         raise ValueError("Utilization has to be between 0 and 1")

    return (power_mw*hours_year*utilization)


def estimate_avg_it_power( ratedpower_mw, utilization, idle_fraction):

    if not math.isfinite(ratedpower_mw) or ratedpower_mw<0:
        raise ValueError("Rated power must be finite and can't be negative")

    if not 0<= utilization<=1:
       raise ValueError("Utilization has to be between 0 and 1")

    if not 0<= idle_fraction <=1:
        raise ValueError("Idle fraction has to be between 0 and 1")

    idle_power=(ratedpower_mw*idle_fraction)

    avg_power_mw= ( idle_power + utilization*(ratedpower_mw-idle_power))
    
    return avg_power_mw

def estimate_annual_facility_energy(avg_it_powermw, pue):

    hour_year=8760

    if not math.isfinite(avg_it_powermw) or avg_it_powermw <0:
        raise ValueError("Avg IT power must be finite and can't be negative")

    if not math.isfinite(pue) or pue<1:
        raise ValueError("PUE must be finite and at least 1")

    facility_powermw= (avg_it_powermw*pue)

    return(facility_powermw*hour_year)


rated_powermw= estimate_power_demand(im3_areasqft=250000, effective_areafactor=1.0, power_density_perft2=162.7)

avg_it_powermw= estimate_avg_it_power(ratedpower_mw=rated_powermw, utilization=0.80,idle_fraction=0.20)

annual_energymwh= estimate_annual_facility_energy(avg_it_powermw=avg_it_powermw, pue=1.40)

    
